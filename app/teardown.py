"""Project teardown — the 'Kill Button'. Dry-run first, backup before delete.

SAFETY MODEL (do not weaken without care — this destroys production state):
  - dry_run is the DEFAULT; execution requires confirm == project name (endpoint).
  - REFUSES: non-project apps, the System bucket, and any project_dir that is not
    exactly <projects_root>/<name> (so a bad path can never `rm -rf` the wrong dir).
  - SKIPS shared assets (an image/cert/volume another app needs) — never removed.
  - BACKS UP first to <projects_root>/backups/<project>/<timestamp>/. Backups are
    `critical` ops ordered before every deletion; if any backup fails the executor
    ABORTS before deleting anything.
  - audits every step via the actions log.

Intentionally NOT removed: TLS certs (certbot-managed, often shared) and images
(shared by nature; prune separately). Those are left and surfaced as 'skipped'.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.blast_radius import compute_blast_radius

PROTECTED_PREFIX = "infradocs-v6-"


class TeardownRefused(Exception):
    pass


def _vol_name(v: Any) -> str:
    return v.get("name") if isinstance(v, dict) else v


def _safe_project_dir(app: Dict[str, Any], projects_root: str) -> Optional[str]:
    """Return the project dir ONLY if it is exactly <projects_root>/<name>."""
    pd = app.get("project_dir")
    if not pd:
        return None
    p = Path(pd).resolve()
    if p.parent == Path(projects_root).resolve() and p.name == app["name"]:
        return str(p)
    return None


def build_plan(
    app: Dict[str, Any], all_apps: List[Dict[str, Any]], *, projects_root: str
) -> Dict[str, Any]:
    """Read-only ordered teardown plan. Skips shared/protected; never executes."""
    name = app["name"]
    refusals: List[str] = []
    if app.get("type") != "project":
        refusals.append("only project applications can be torn down")
    if name == "System":
        refusals.append("refusing to tear down the System bucket")

    safe_dir = _safe_project_dir(app, projects_root)
    if app.get("project_dir") and not safe_dir:
        refusals.append(
            f"project_dir {app.get('project_dir')} is not {projects_root}/{name} "
            "— refusing to remove it"
        )

    br = compute_blast_radius(app, all_apps)
    shared = {i["name"] for i in br["items"] if i["shared"]}
    skipped: List[Dict[str, Any]] = [
        {"name": i["name"], "category": i["category"],
         "reason": "shared with " + ", ".join(i["shared_with"])}
        for i in br["items"] if i["shared"]
    ]

    vols = [v for v in app.get("volumes", []) if _vol_name(v) not in shared]
    ops: List[Dict[str, Any]] = []

    # ---- backups first (critical: failure aborts the whole teardown) ----
    if safe_dir:
        ops.append({"op": "backup_dir", "target": safe_dir,
                    "label": f"backup {safe_dir}", "critical": True})
    for v in vols:
        vn = _vol_name(v)
        ops.append({"op": "backup_volume", "target": vn,
                    "mountpoint": v.get("mountpoint") if isinstance(v, dict) else None,
                    "label": f"backup volume {vn}", "critical": True})

    # ---- teardown (ordered: runtime -> nginx -> data) ----
    for c in app.get("containers", []):
        if c in shared or str(c).startswith(PROTECTED_PREFIX):
            continue
        ops.append({"op": "remove_container", "target": c,
                    "label": f"stop + remove container {c}", "destructive": True})

    if app.get("compose_file"):
        ops.append({"op": "compose_down", "target": app["compose_file"],
                    "label": "docker compose down (volumes kept)", "destructive": True})

    for u in app.get("systemd_units", []):
        if str(u).startswith(PROTECTED_PREFIX):
            skipped.append({"name": u, "category": "systemd_unit", "reason": "self-protected"})
            continue
        ops.append({"op": "disable_unit", "target": u,
                    "label": f"disable + stop {u}", "destructive": True})

    seen_cfg = set()
    for nd in app.get("nginx_detail", []):
        cf = nd.get("config_file")
        if nd.get("server_name") in shared or not cf or cf in seen_cfg:
            continue
        seen_cfg.add(cf)
        ops.append({"op": "remove_nginx", "target": cf,
                    "server_name": nd.get("server_name"),
                    "label": f"remove nginx {nd.get('server_name')} ({cf})", "destructive": True})
    if seen_cfg:
        ops.append({"op": "reload_nginx", "target": "nginx",
                    "label": "nginx -s reload", "destructive": True})

    for v in vols:  # after backup
        vn = _vol_name(v)
        ops.append({"op": "remove_volume", "target": vn,
                    "label": f"remove volume {vn}", "destructive": True, "data_loss": True})

    if safe_dir:  # after backup
        ops.append({"op": "remove_dir", "target": safe_dir,
                    "label": f"rm -rf {safe_dir}", "destructive": True, "data_loss": True})

    return {
        "project": name,
        "refusals": refusals,
        "skipped": skipped,
        "ops": ops,
        "data_loss": any(o.get("data_loss") for o in ops),
        "blast_radius": br,
        "projects_root": projects_root,
    }


# ----------------------------- execution -----------------------------------


def _run(cmd: List[str], timeout: int = 120) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return {"status": "success" if p.returncode == 0 else "failed",
                "rc": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-2000:]}
    except Exception as e:
        return {"status": "failed", "rc": None, "stdout": "", "stderr": str(e)}


def _run_op(op: Dict[str, Any], backup_dir: str, projects_root: str, name: str) -> Dict[str, Any]:
    t = op["op"]
    tgt = op["target"]
    if t == "backup_dir":
        parent = str(Path(tgt).parent)
        base = Path(tgt).name
        return _run(["tar", "-czf", f"{backup_dir}/files.tar.gz", "-C", parent, base], timeout=600)
    if t == "backup_volume":
        mp = op.get("mountpoint") or f"/var/lib/docker/volumes/{tgt}/_data"
        return _run(["sudo", "-n", "tar", "-czf", f"{backup_dir}/vol-{tgt}.tar.gz", "-C", mp, "."], timeout=600)
    if t == "remove_container":
        return _run(["docker", "rm", "-f", tgt])
    if t == "compose_down":
        return _run(["docker", "compose", "-f", tgt, "down"])
    if t == "disable_unit":
        return _run(["sudo", "-n", "systemctl", "disable", "--now", tgt], timeout=60)
    if t == "remove_nginx":
        return _run(["sudo", "-n", "rm", "-f", tgt])
    if t == "reload_nginx":
        return _run(["sudo", "-n", "nginx", "-s", "reload"])
    if t == "remove_volume":
        return _run(["docker", "volume", "rm", tgt])
    if t == "remove_dir":
        # Defense in depth: re-validate the path right before rm -rf.
        p = Path(tgt).resolve()
        if p.parent != Path(projects_root).resolve() or p.name != name:
            return {"status": "failed", "rc": None, "stdout": "",
                    "stderr": f"refusing rm -rf {tgt}: not {projects_root}/{name}"}
        return _run(["rm", "-rf", tgt], timeout=120)
    return {"status": "failed", "rc": None, "stdout": "", "stderr": f"unknown op {t}"}


def execute_plan(
    plan: Dict[str, Any], db, actor: str, *, projects_root: str, now: Optional[datetime] = None
) -> Dict[str, Any]:
    name = plan["project"]
    if plan["refusals"]:
        raise TeardownRefused("; ".join(plan["refusals"]))

    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{projects_root}/backups/{name}/{ts}"
    os.makedirs(backup_dir, exist_ok=True)

    results: List[Dict[str, Any]] = []
    aborted = False
    for op in plan["ops"]:
        if aborted:
            results.append({**op, "status": "skipped", "detail": "aborted after a backup failure"})
            continue
        r = _run_op(op, backup_dir, projects_root, name)
        row = {**op, **r}
        results.append(row)
        _audit(db, actor, name, op, r)
        if op.get("critical") and r["status"] != "success":
            aborted = True
            row["detail"] = "BACKUP FAILED — aborting teardown, no deletion performed"
    return {"project": name, "backup_dir": backup_dir, "aborted": aborted, "results": results}


def _audit(db, actor: str, name: str, op: Dict[str, Any], r: Dict[str, Any]) -> None:
    try:
        db.record_action({
            "actor": actor,
            "asset_id": None,
            "asset_name": str(op.get("target")),
            "category": "teardown",
            "project": name,
            "action": f"teardown:{op['op']}",
            "args": {"project": name},
            "status": r.get("status"),
            "return_code": r.get("rc"),
            "stdout": (r.get("stdout") or "")[-2000:],
            "stderr": (r.get("stderr") or "")[-2000:],
            "duration_ms": 0,
            "refused_reason": None,
        })
    except Exception:
        pass
