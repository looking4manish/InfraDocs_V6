"""Gossip + failover loop. Drives the pure logic in app.cluster against this node's
own Mongo (no shared DB). Gated by federation.cluster_enabled, so it is inert until a
real fleet turns it on.

Each round (every health_interval): pull /api/cluster/health from every known peer,
fold the replies into the local roster (self-heal), then run evaluate_cluster and apply
the decision (become/relinquish primary, follow the leader). The election grace — one
full round after primary-loss is first seen — is tracked here in `_election`.
"""

import asyncio
from datetime import datetime, timezone

from app import cluster as CC
from app import federation as F

# Per-process election timing state (not persisted — it's only a debounce).
_election = {"primary_lost_since": None}


def _peer_health(address: str, timeout: int = 6) -> dict:
    return F._get_json(address.rstrip("/") + "/api/cluster/health", timeout=timeout)


def run_round(db, cfg, now=None, ping=_peer_health) -> dict:
    """One gossip+evaluate+apply cycle. Returns the decision (for logging/tests)."""
    now = now or datetime.now(timezone.utc)
    node_id = cfg.server.id
    timeout = cfg.federation.unreachable_after_seconds
    interval = cfg.federation.health_interval_seconds

    s = db.db.cluster.find_one({"_id": "self"}) or {}
    roster = {n["node_id"]: n for n in db.db.cluster_nodes.find({}, {"_id": 0})}

    # --- gossip: pull every known peer's health, self-heal the roster ---------
    override_seen = False
    for nid, rec in list(roster.items()):
        addr = rec.get("address")
        if not addr or nid == node_id:
            continue
        try:
            msg = ping(addr)
            CC.merge_gossip(roster, msg, now)
            if msg.get("is_primary") and msg.get("override"):
                override_seen = True
        except Exception:  # noqa: BLE001 — peer unreachable; leave its last_seen stale
            pass
    # persist the refreshed roster
    for nid, rec in roster.items():
        if nid == node_id:
            continue
        db.db.cluster_nodes.update_one({"node_id": nid}, {"$set": rec}, upsert=True)

    # --- build the node list for evaluation (self always reachable) -----------
    nodes = [{"node_id": node_id, "priority": s.get("priority"), "last_seen": now,
              "is_primary": bool(s.get("is_primary")), "self": True}]
    for nid, rec in roster.items():
        if nid == node_id:
            continue
        nodes.append({"node_id": nid, "priority": rec.get("priority"),
                      "last_seen": rec.get("last_seen"), "is_primary": bool(rec.get("is_primary")),
                      "self": False})

    override = bool(s.get("override")) or override_seen

    # --- election grace: wait one full round after primary-loss is first seen --
    reach = CC.reachable_nodes(nodes, now, timeout)
    primary_visible = any(n.get("is_primary") for n in reach)
    if primary_visible or override:
        _election["primary_lost_since"] = None
        grace_elapsed = True
    else:
        if _election["primary_lost_since"] is None:
            _election["primary_lost_since"] = now
        grace_elapsed = (now - _election["primary_lost_since"]).total_seconds() >= interval

    decision = CC.evaluate_cluster(nodes, node_id, now, override=override,
                                   election_grace_elapsed=grace_elapsed, timeout=timeout)

    # --- apply ---------------------------------------------------------------
    if decision["action"] == "promote_self":
        db.db.cluster.update_one({"_id": "self"}, {"$set": {"is_primary": True}}, upsert=True)
        _election["primary_lost_since"] = None
    elif decision["action"] in ("step_down", "follow", "no_leader"):
        if s.get("is_primary"):
            db.db.cluster.update_one({"_id": "self"}, {"$set": {"is_primary": False}}, upsert=True)
    db.db.cluster.update_one({"_id": "self"}, {"$set": {"override_seen": override_seen}}, upsert=True)
    db.db.settings.update_one({"_id": "app"}, {"$set": {"primary_node": decision.get("current_leader")}}, upsert=True)
    return decision


async def loop(cfg, db, logger):
    interval = cfg.federation.health_interval_seconds
    while True:
        try:
            d = await asyncio.to_thread(run_round, db, cfg)
            logger.debug("cluster round: %s", d.get("action"))
        except Exception as e:  # noqa: BLE001 — never let a blip kill the loop
            logger.warning("cluster round failed: %s", e)
        await asyncio.sleep(interval)
