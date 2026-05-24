"""Ports registry (Phase 7B).

Builds an evidence-based port inventory by walking the freshly-scanned
asset stream. Each row is a unique (port, protocol) pair carrying:

  - state: "in_use" if anything is currently listening on it, otherwise
           "declared" (declared in compose, nginx upstream, nginx listen, ...)
  - owner_project / owner_app_id: which application owns the port. Inferred
    from listening process, host_port → container, nginx → upstream → port,
    and the Phase 7 project/System routing.
  - evidence_sources: list of {kind, source} tuples explaining why the
    registry knows about this port. Multiple sources can stack (e.g.,
    declared in compose AND currently listening).
  - process / pid / local_address: only when state == "in_use".

The on-demand `probe()` helper is *not* persisted — it just runs `ss` and
filters to the requested range. Used by GET /api/ports/probe.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


PortKey = Tuple[int, str]  # (port, "tcp" | "udp")


def _add_evidence(row: Dict[str, Any], kind: str, source: str) -> None:
    """Append an evidence entry, dedup on (kind, source)."""
    key = (kind, source)
    seen = {(e["kind"], e["source"]) for e in row["evidence_sources"]}
    if key not in seen:
        row["evidence_sources"].append({"kind": kind, "source": source})


def _new_row(port: int, proto: str) -> Dict[str, Any]:
    return {
        "port": port,
        "protocol": proto,
        "state": "declared",  # upgraded to in_use if a listener appears
        "process": None,
        "pid": None,
        "local_address": None,
        "owner_project": None,
        "owner_app_id": None,
        "evidence_sources": [],
    }


def _project_to_app_id(project: str, server_id: str) -> str:
    return f"{server_id}:app:{project}"


def _container_app_name(
    container_asset: Dict[str, Any],
    valid_projects: Set[str],
) -> str:
    """Replicates the correlator's container-to-app routing for one asset."""
    meta = container_asset["metadata"]
    compose_proj = meta.get("compose_project")
    if compose_proj and compose_proj in valid_projects:
        return compose_proj
    proj = container_asset.get("project")
    if proj and proj in valid_projects and proj != "System":
        return proj
    return "System"


def build_ports_registry(
    assets: List[Dict[str, Any]],
    *,
    server_id: str,
    valid_projects: Iterable[str],
) -> List[Dict[str, Any]]:
    """Walk assets and return one row per unique (port, protocol)."""
    valid = set(valid_projects)
    rows: Dict[PortKey, Dict[str, Any]] = {}

    def _get(port: int, proto: str) -> Dict[str, Any]:
        proto = proto.lower()
        key = (port, proto)
        if key not in rows:
            rows[key] = _new_row(port, proto)
        return rows[key]

    # ---- listening ports (from `ss -tulpnH`) -------------------------------
    for p in assets:
        if p.get("category") != "network_port":
            continue
        meta = p["metadata"]
        port = meta.get("port")
        if not isinstance(port, int):
            continue
        proto = (meta.get("protocol") or "tcp").lower()
        # normalize: tcp6 / udp6 collapse to tcp / udp (same port number range)
        if proto in ("tcp6",):
            proto = "tcp"
        elif proto in ("udp6",):
            proto = "udp"

        row = _get(port, proto)
        row["state"] = "in_use"
        row["process"] = meta.get("process") or row["process"]
        row["pid"] = meta.get("pid") or row["pid"]
        row["local_address"] = meta.get("local_address") or row["local_address"]

        # Owner from the port asset's own project tag (PortScanner reads
        # /proc/<pid>/cwd to set this — see app/scanners/port.py).
        proj = p.get("project") or "System"
        if proj in valid and not row["owner_project"]:
            row["owner_project"] = proj

        _add_evidence(
            row,
            "listening",
            meta.get("process") or f"pid={meta.get('pid', '?')}",
        )

    # ---- container host_ports (compose-declared, but also "in_use" if
    #      the container is running) ----------------------------------------
    for c in assets:
        if c.get("category") != "docker_container":
            continue
        meta = c["metadata"]
        running = c.get("status") == "running"
        app_name = _container_app_name(c, valid)
        port_entries = meta.get("ports") or []
        for pm in port_entries:
            hp = pm.get("host_port")
            try:
                port = int(hp) if hp is not None else None
            except (TypeError, ValueError):
                port = None
            if port is None:
                continue
            # ports[]'s container_port is "8080/tcp" — extract the proto.
            cp = (pm.get("container_port") or "").lower()
            proto = "tcp"
            if "/" in cp:
                proto = cp.split("/", 1)[1] or "tcp"
            row = _get(port, proto)
            if running:
                row["state"] = "in_use"
            if not row["owner_project"] and app_name:
                row["owner_project"] = app_name
            _add_evidence(row, "container", f"{c['name']}:{cp or port}")

    # ---- nginx: upstream_port (proxy_pass localhost:NNN) and listen_ports --
    for ng in assets:
        if ng.get("category") != "nginx_server_block":
            continue
        meta = ng["metadata"]
        # upstream_port: the *backend* port the vhost proxies to
        up = meta.get("upstream_port")
        if isinstance(up, int):
            row = _get(up, "tcp")
            _add_evidence(row, "nginx_upstream", ng["name"])
        # listen_ports: what nginx itself listens on (usually 80/443)
        for lp in meta.get("listen_ports") or []:
            if not isinstance(lp, int):
                continue
            row = _get(lp, "tcp")
            _add_evidence(row, "nginx_listen", ng["name"])
            # nginx serves these so owner is nginx itself (System) unless
            # the port already has an owner from another evidence source.

    # ---- systemd: parse Environment / ExecStart for declared ports --------
    # (lightweight: pull integer-looking PORT= values out of environment_keys
    # plus any --port N tokens in exec_start)
    # Only match explicit port flags. The `:N` form was tempting but it
    # eats timestamp fragments out of systemd's ExecStart= rendering
    # (`start_time=[Sun 2026-05-24 16:07:36 UTC]` → "07", "36"...).
    port_token_re = re.compile(r"(?:--port[= ]|--port=|\s-p[= ])(\d{2,5})\b")
    for s in assets:
        if s.get("category") not in ("systemd_service", "systemd_timer"):
            continue
        meta = s["metadata"]
        exec_start = meta.get("exec_start") or ""
        seen: Set[int] = set()
        for m in port_token_re.finditer(exec_start):
            try:
                p = int(m.group(1))
            except ValueError:
                continue
            if 1 <= p <= 65535:
                seen.add(p)
        for port in seen:
            row = _get(port, "tcp")
            proj = s.get("project") or "System"
            if proj in valid and not row["owner_project"]:
                row["owner_project"] = proj
            _add_evidence(row, "systemd_exec", s["name"])

    # ---- finalize: derive owner_app_id and a stable port_id ---------------
    out = []
    for (port, proto), row in rows.items():
        owner = row["owner_project"] or "System"
        row["owner_project"] = owner
        row["owner_app_id"] = _project_to_app_id(owner, server_id)
        row["port_id"] = f"{server_id}:port:{proto}:{port}"
        out.append(row)
    out.sort(key=lambda r: (r["port"], r["protocol"]))
    return out


# --------------------------- on-demand probe --------------------------------


def probe(
    start: int, end: int, *, proto: str = "tcp"
) -> List[Dict[str, Any]]:
    """Live snapshot via `ss`. Not persisted. Used by /api/ports/probe."""
    if start < 1 or end > 65535 or start > end:
        raise ValueError("invalid range")
    flag = "-tlnH" if proto == "tcp" else "-ulnH"
    try:
        result = subprocess.run(
            ["ss", flag],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as e:
        raise RuntimeError(f"ss failed: {e}") from e

    rows: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        if ":" not in local:
            continue
        try:
            port = int(local.rsplit(":", 1)[1])
        except ValueError:
            continue
        if port < start or port > end or port in seen:
            continue
        seen.add(port)
        rows.append(
            {
                "port": port,
                "protocol": proto,
                "state": "in_use",
                "local_address": local,
            }
        )

    # Pad with "free" rows so the consumer gets a complete range view.
    out = []
    in_use = {r["port"]: r for r in rows}
    for port in range(start, end + 1):
        if port in in_use:
            out.append(in_use[port])
        else:
            out.append(
                {
                    "port": port,
                    "protocol": proto,
                    "state": "free",
                    "local_address": None,
                }
            )
    return out
