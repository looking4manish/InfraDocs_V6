"""Operational actions (Phase 8).

A small dispatcher that maps (asset_category, action) → a callable that
actually performs the action against the host (docker SDK, systemctl,
nginx, etc.). Returns a uniform `ActionResult` so the API layer can log
and return without caring which subsystem was touched.

Safety rails in this module:
  - allow-list per asset category (unknown action → ActionNotAllowed)
  - explicit refusal to act on `infradocs-v6-*` so the API can't kill
    itself mid-request
  - logs() is capped at 1000 lines

Everything else (sudo permissions, container ownership) is enforced by
the OS. The dispatcher just runs the command and reports stdout/stderr.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import docker
from docker.errors import APIError, DockerException, NotFound


# ----------------------- allow-list per category ----------------------------

# Card & Action Registry (Phase 3.5) — single source of truth for what each
# category permits. `allowed` = every fireable action; `destructive` = subset
# that needs a confirm gate; `self_protect` = enforce infradocs-v6-* refusal.
# ALLOWED_ACTIONS is derived below so existing consumers keep working unchanged.
ACTION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "docker_container": {
        "allowed": {"start", "stop", "restart", "logs", "inspect", "stats"},
        "destructive": {"stop", "restart"},
        "self_protect": True,
    },
    "docker_compose": {
        "allowed": {"up", "down", "restart"},
        "destructive": {"down", "restart"},
        "self_protect": True,
    },
    "systemd_service": {
        "allowed": {"start", "stop", "restart", "logs", "status", "enable", "disable"},
        "destructive": {"stop", "restart", "disable"},
        "self_protect": True,
    },
    "systemd_timer": {
        "allowed": {"start", "stop", "restart", "status", "enable", "disable"},
        "destructive": {"stop", "restart", "disable"},
        "self_protect": True,
    },
    "nginx_server_block": {
        "allowed": {"test", "reload"},
        "destructive": {"reload"},
        "self_protect": False,
    },
    "docker_image": {
        "allowed": {"pull"},
        "destructive": set(),
        "self_protect": False,
    },
}

# Derived view — preserves the original API/dispatch consumers verbatim.
ALLOWED_ACTIONS: Dict[str, set] = {
    cat: set(spec["allowed"]) for cat, spec in ACTION_REGISTRY.items()
}

# Destructive map (used by /api/actions/allowed additively, and by the UI).
DESTRUCTIVE_ACTIONS: Dict[str, set] = {
    cat: set(spec.get("destructive", set())) for cat, spec in ACTION_REGISTRY.items()
}

# Refuse to act on these — would kill the API mid-request.
SELF_PROTECT_PREFIXES = ("infradocs-v6-",)


class ActionError(Exception):
    pass


class ActionNotAllowed(ActionError):
    pass


class SelfActionRefused(ActionError):
    pass


@dataclass
class ActionResult:
    status: str  # "success" | "failed"
    stdout: str = ""
    stderr: str = ""
    return_code: Optional[int] = None
    duration_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


# ----------------------- docker container actions ---------------------------


def _docker_client():
    try:
        return docker.from_env()
    except DockerException as e:
        raise ActionError(f"docker daemon unreachable: {e}")


def _act_docker_container(
    asset: Dict[str, Any], action: str, args: Dict[str, Any]
) -> ActionResult:
    client = _docker_client()
    container_id = asset.get("metadata", {}).get("container_id") or asset["name"]
    try:
        container = client.containers.get(container_id)
    except NotFound:
        raise ActionError(f"container not found: {container_id}")

    if action == "start":
        container.start()
        return ActionResult(status="success", stdout=f"started {container.name}")
    if action == "stop":
        timeout = int(args.get("timeout", 10))
        container.stop(timeout=timeout)
        return ActionResult(status="success", stdout=f"stopped {container.name}")
    if action == "restart":
        timeout = int(args.get("timeout", 10))
        container.restart(timeout=timeout)
        return ActionResult(status="success", stdout=f"restarted {container.name}")
    if action == "logs":
        tail = min(int(args.get("tail", 100)), 1000)
        raw = container.logs(tail=tail).decode("utf-8", errors="replace")
        return ActionResult(
            status="success",
            stdout=raw,
            details={"tail": tail, "lines": raw.count("\n")},
        )
    if action == "inspect":
        attrs = container.attrs
        import json as _json
        return ActionResult(
            status="success",
            stdout=_json.dumps(attrs, indent=2, default=str),
            details={"state": attrs.get("State", {})},
        )
    if action == "stats":
        st = container.stats(stream=False)
        import json as _json
        return ActionResult(
            status="success",
            stdout=_json.dumps(st, indent=2, default=str),
            details={"read": st.get("read")},
        )
    raise ActionNotAllowed(action)


# ----------------------- docker compose actions -----------------------------


def _act_docker_compose(
    asset: Dict[str, Any], action: str, args: Dict[str, Any]
) -> ActionResult:
    """Run `docker compose <action>` in the compose file's directory."""
    file_path = asset.get("metadata", {}).get("file_path")
    if not file_path:
        raise ActionError("compose file path missing")

    sub = {"up": ["up", "-d"], "down": ["down"], "restart": ["restart"]}.get(action)
    if sub is None:
        raise ActionNotAllowed(action)

    cmd = ["docker", "compose", "-f", file_path] + sub
    return _run_subprocess(cmd, timeout=120)


# ----------------------- systemd actions ------------------------------------


def _act_systemd(
    asset: Dict[str, Any], action: str, args: Dict[str, Any]
) -> ActionResult:
    name = asset["name"]
    if any(name.startswith(p) for p in SELF_PROTECT_PREFIXES):
        raise SelfActionRefused(f"refusing to act on protected unit: {name}")

    if action in ("start", "stop", "restart", "enable", "disable"):
        cmd = ["sudo", "-n", "systemctl", action, name]
        return _run_subprocess(cmd, timeout=30)
    if action == "status":
        cmd = ["systemctl", "status", "--no-pager", "-n", "0", name]
        return _run_subprocess(cmd, timeout=10, allow_nonzero=True)
    if action == "logs":
        tail = min(int(args.get("tail", 100)), 1000)
        cmd = [
            "journalctl",
            "-u",
            name,
            "--no-pager",
            "-n",
            str(tail),
        ]
        return _run_subprocess(cmd, timeout=15)
    raise ActionNotAllowed(action)


# ----------------------- nginx actions --------------------------------------


def _act_nginx(
    asset: Dict[str, Any], action: str, args: Dict[str, Any]
) -> ActionResult:
    if action == "test":
        # nginx -t is read-only; no sudo needed if msinha can read configs.
        return _run_subprocess(["sudo", "-n", "nginx", "-t"], timeout=10,
                               allow_nonzero=True)
    if action == "reload":
        return _run_subprocess(
            ["sudo", "-n", "nginx", "-s", "reload"], timeout=10
        )
    raise ActionNotAllowed(action)


# ----------------------- docker image actions -------------------------------


def _act_docker_image(
    asset: Dict[str, Any], action: str, args: Dict[str, Any]
) -> ActionResult:
    client = _docker_client()
    if action == "pull":
        ref = (asset.get("metadata", {}).get("tags") or [asset.get("name")])[0]
        if not ref:
            raise ActionError("image reference missing")
        try:
            client.images.pull(ref)
        except (APIError, DockerException) as e:
            raise ActionError(f"pull failed: {e}")
        return ActionResult(status="success", stdout=f"pulled {ref}")
    raise ActionNotAllowed(action)


# ----------------------- subprocess runner ----------------------------------


def _run_subprocess(
    cmd: List[str], *, timeout: int, allow_nonzero: bool = False
) -> ActionResult:
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return ActionResult(
            status="failed",
            stderr=f"timeout after {timeout}s: {shlex.join(cmd)}",
            duration_ms=int((time.time() - start) * 1000),
        )
    except FileNotFoundError as e:
        return ActionResult(
            status="failed",
            stderr=f"command not found: {e}",
            duration_ms=int((time.time() - start) * 1000),
        )
    duration = int((time.time() - start) * 1000)
    ok = allow_nonzero or proc.returncode == 0
    return ActionResult(
        status="success" if ok else "failed",
        stdout=proc.stdout,
        stderr=proc.stderr,
        return_code=proc.returncode,
        duration_ms=duration,
    )


# ----------------------- top-level dispatch ---------------------------------


_DISPATCH = {
    "docker_container": _act_docker_container,
    "docker_compose": _act_docker_compose,
    "systemd_service": _act_systemd,
    "systemd_timer": _act_systemd,
    "nginx_server_block": _act_nginx,
    "docker_image": _act_docker_image,
}


def dispatch(
    asset: Dict[str, Any], action: str, args: Optional[Dict[str, Any]] = None
) -> ActionResult:
    """Run `action` against `asset`. Raises ActionNotAllowed / ActionError."""
    category = asset.get("category")
    handler = _DISPATCH.get(category)
    if not handler:
        raise ActionNotAllowed(
            f"category '{category}' has no operational actions"
        )
    # Centralized self-protect: refuse infradocs-v6-* for every category,
    # not just systemd, so the API can never act on itself mid-request.
    if ACTION_REGISTRY.get(category, {}).get("self_protect"):
        _nm = asset.get("name", "")
        if any(_nm.startswith(_p) for _p in SELF_PROTECT_PREFIXES):
            raise SelfActionRefused(
                f"refusing to act on protected asset: {_nm}"
            )
    if action not in ALLOWED_ACTIONS.get(category, set()):
        raise ActionNotAllowed(
            f"action '{action}' not allowed for category '{category}' "
            f"(allowed: {sorted(ALLOWED_ACTIONS.get(category, []))})"
        )

    start = time.time()
    try:
        result = handler(asset, action, args or {})
    except ActionNotAllowed:
        raise
    except SelfActionRefused:
        raise
    except ActionError as e:
        return ActionResult(
            status="failed",
            stderr=str(e),
            duration_ms=int((time.time() - start) * 1000),
        )
    except (APIError, DockerException) as e:
        return ActionResult(
            status="failed",
            stderr=f"docker: {e}",
            duration_ms=int((time.time() - start) * 1000),
        )
    if result.duration_ms == 0:
        result.duration_ms = int((time.time() - start) * 1000)
    return result
