"""Cluster coordination endpoints — gossip health, cluster state, override, and the
guarded manual promote (the restore path). No shared DB: each node persists its own
view in its own Mongo (`cluster` self-doc + `cluster_nodes` roster)."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import cluster as CC
from app.api.dependencies import get_config, get_db, verify_auth
from app.core.config_loader import Config
from app.core.db_manager import DBManager

router = APIRouter()


def _self(db: DBManager) -> dict:
    return db.db.cluster.find_one({"_id": "self"}) or {}


def _roster(db: DBManager) -> list:
    return list(db.db.cluster_nodes.find({}, {"_id": 0}))


def _set_self(db: DBManager, patch: dict) -> None:
    db.db.cluster.update_one({"_id": "self"}, {"$set": patch}, upsert=True)


@router.get("/health")
def health(cfg: Config = Depends(get_config), db: DBManager = Depends(get_db)):
    """The gossip message this node emits when a peer health-checks it: its own id +
    priority + last-scan time + whether it serves as primary + override, plus the peers
    it knows (so priorities propagate transitively in one round). Unauthenticated."""
    s = _self(db)
    last_scan = db.db.scan_logs.find_one({}, sort=[("created_at", -1)])
    return {
        "node_id": cfg.server.id,
        "priority": s.get("priority"),
        "address": s.get("address"),
        "is_primary": bool(s.get("is_primary")),
        "override": bool(s.get("override")),
        "last_scan_ts": (last_scan or {}).get("created_at"),
        "peers": [
            {"node_id": n["node_id"], "priority": n.get("priority"), "address": n.get("address")}
            for n in _roster(db)
        ],
    }


@router.get("/state")
def state(_: str = Depends(verify_auth), cfg: Config = Depends(get_config), db: DBManager = Depends(get_db)):
    """Full cluster view for the Servers lens: this node, the current leader, every
    known node with priority + reachability, fleet size, and whether we hold a majority."""
    s = _self(db)
    now = datetime.now(timezone.utc)
    timeout = cfg.federation.unreachable_after_seconds
    node_id = cfg.server.id

    nodes = [{
        "node_id": node_id, "priority": s.get("priority"), "address": s.get("address"),
        "is_primary": bool(s.get("is_primary")), "reachable": True, "self": True,
        "last_seen": now, "last_scan_ts": s.get("last_scan_ts"),
    }]
    for n in _roster(db):
        if n["node_id"] == node_id:
            continue
        age = CC._age(now, n.get("last_seen"))
        nodes.append({
            "node_id": n["node_id"], "priority": n.get("priority"), "address": n.get("address"),
            "is_primary": bool(n.get("is_primary")), "reachable": age <= timeout, "self": False,
            "last_seen": n.get("last_seen"), "last_scan_ts": n.get("last_scan_ts"),
        })

    reachable = [n for n in nodes if n["reachable"]]
    leader = next((n["node_id"] for n in reachable if n["is_primary"]), None)
    return {
        "node_id": node_id,
        "priority": s.get("priority"),
        "is_primary": bool(s.get("is_primary")),
        "override": bool(s.get("override")),
        "current_leader": leader,
        "majority": CC.has_majority(len(reachable), len(nodes)),
        "nodes": nodes,
    }


class OverrideRequest(BaseModel):
    value: bool


@router.post("/override")
def override(req: OverrideRequest, _: str = Depends(verify_auth), db: DBManager = Depends(get_db)):
    """Pin/unpin the current primary. While set, no node initiates an election (it's
    broadcast in /health and remembered by peers). The manual escape hatch."""
    _set_self(db, {"override": bool(req.value)})
    return {"ok": True, "override": bool(req.value)}


class PromoteRequest(BaseModel):
    force: bool = False


@router.post("/promote")
def promote(
    req: PromoteRequest,
    actor: str = Depends(verify_auth),
    cfg: Config = Depends(get_config),
    db: DBManager = Depends(get_db),
):
    """Manually promote THIS node to primary (the failover-restore path). Guarded:
      - refuse if a LIVE primary is visible (a reachable peer serving as primary);
      - if some nodes are UNREACHABLE, do NOT silently promote — return needs_force
        with the two-primaries warning;
      - force=true (explicit confirm) promotes despite unreachable nodes, but NEVER
        against a confirmed-live primary."""
    node_id = cfg.server.id
    now = datetime.now(timezone.utc)
    timeout = cfg.federation.unreachable_after_seconds

    live_primary, unreachable = None, []
    for n in _roster(db):
        if n["node_id"] == node_id:
            continue
        reachable = CC._age(now, n.get("last_seen")) <= timeout
        if reachable and n.get("is_primary"):
            live_primary = n["node_id"]
        elif not reachable:
            unreachable.append(n["node_id"])

    if live_primary:
        return {"promoted": False, "leader": live_primary,
                "reason": f"a live primary is visible: {live_primary} — refuse (use override/failover instead)"}

    if unreachable and not req.force:
        return {
            "promoted": False, "needs_force": True, "unreachable": unreachable,
            "warning": ("the current primary can't be confirmed down — these nodes are "
                        f"unreachable: {unreachable}. Forcing may create two primaries. "
                        "Re-submit with force=true only if you are certain the old primary is down."),
        }

    # Promote: this node becomes primary; clear any stale primary flags in our roster.
    _set_self(db, {"is_primary": True, "node_id": node_id, "promoted_at": now,
                   "promoted_by": actor, "forced": bool(req.force)})
    db.db.cluster_nodes.update_many({}, {"$set": {"is_primary": False}})
    db.db.settings.update_one({"_id": "app"}, {"$set": {"primary_node": node_id}}, upsert=True)
    return {"promoted": True, "forced": bool(req.force), "leader": node_id,
            "warning": ("force-promoted despite unreachable nodes — verify no second primary is running."
                        if (req.force and unreachable) else None)}
