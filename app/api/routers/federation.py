"""Federation — a primary aggregates secondaries' scans over the Tailscale mesh.

Every node can reach every other node directly (tailnet), so the old outbound
command-queue + poll + reap machinery has been removed. What remains here is the
data plane (a primary ingesting a secondary's scan) + token minting + the server
list. Enrollment reachability lives below (added with the direct model); leader
election lives in app/cluster_lease.py.
"""

import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app import cluster_lease as CL
from app import federation as F
from app.api.dependencies import get_config, get_db, verify_auth
from app.core.config_loader import Config
from app.core.db_manager import DBManager

router = APIRouter()


class MintRequest(BaseModel):
    server_id: str


@router.post("/tokens")
def mint_token(req: MintRequest, actor: str = Depends(verify_auth), db: DBManager = Depends(get_db)):
    """Primary mints a join token for a new secondary (shown in 'Add a server')."""
    token = secrets.token_urlsafe(24)
    db.db.join_tokens.insert_one({
        "token": token,
        "server_id": req.server_id,
        "created_at": datetime.now(timezone.utc),
        "created_by": actor,
    })
    return {"token": token, "server_id": req.server_id}


@router.get("/servers")
def list_servers(_: str = Depends(verify_auth), db: DBManager = Depends(get_db)):
    servers = list(db.db.federation_servers.find({}, {"_id": 0}))
    return {"servers": servers, "count": len(servers)}


def _valid_token(db: DBManager, server_id: str, token: Optional[str]) -> bool:
    if not token:
        return False
    rec = db.db.join_tokens.find_one({"token": token})
    return bool(rec and rec.get("server_id") == server_id)


class IngestRequest(BaseModel):
    server_id: str
    assets: List[dict] = []
    applications: List[dict] = []
    scan_meta: Optional[dict] = None


@router.post("/ingest")
def ingest(
    req: IngestRequest,
    x_join_token: Optional[str] = Header(None),
    db: DBManager = Depends(get_db),
):
    if not _valid_token(db, req.server_id, x_join_token):
        raise HTTPException(status_code=401, detail="invalid or missing join token")
    sid = req.server_id

    def _clean(docs):
        for d in docs:
            d.pop("_id", None)        # let the primary assign its own ids
            d["server_id"] = sid       # enforce scope — a token can't write another server
        return docs

    # Scoped replace: swap out just this server's slice, leave others intact.
    db.db.assets.delete_many({"server_id": sid})
    assets = _clean(req.assets)
    if assets:
        db.db.assets.insert_many(assets)
    db.db.applications.delete_many({"server_id": sid})
    apps = _clean(req.applications)
    if apps:
        db.db.applications.insert_many(apps)

    db.db.federation_servers.update_one(
        {"server_id": sid},
        {"$set": {
            "server_id": sid,
            "last_seen": datetime.now(timezone.utc),
            "asset_count": len(assets),
            "app_count": len(apps),
        }},
        upsert=True,
    )
    return {"ok": True, "server_id": sid, "assets": len(assets), "applications": len(apps)}


# ===========================================================================
# Direct (mesh) model: reachability handshake + leader election.
# ===========================================================================


@router.get("/ping")
def ping(cfg: Config = Depends(get_config), db: DBManager = Depends(get_db)):
    """Unauthenticated identity + lease view. Used (a) by a primary connecting BACK
    to a secondary during the enroll handshake, and (b) by /promote to probe peers.
    Returns only non-sensitive identity/leadership info."""
    return {
        "ok": True,
        "server_id": cfg.server.id,
        "role": _settings(db).get("role"),
        "leader": CL.lease_state(db.db),
    }


def _settings(db: DBManager) -> dict:
    return db.db.settings.find_one({"_id": "app"}) or {}


class EnrollRequest(BaseModel):
    server_id: str
    secondary_url: str   # the secondary's own tailnet address, for the back-connection
    join_token: str


@router.post("/enroll")
def enroll(req: EnrollRequest, db: DBManager = Depends(get_db)):
    """Primary-side of the bidirectional handshake. The request arriving proves
    secondary->primary. We then connect BACK to secondary_url/ping to prove
    primary->secondary. Enrollment is recorded ONLY if BOTH directions pass."""
    if not _valid_token(db, req.server_id, req.join_token):
        raise HTTPException(status_code=401, detail="invalid or missing join token")

    secondary_to_primary = True  # this request reached us
    primary_to_secondary = False
    reason = None
    try:
        pong = F.ping_node(req.secondary_url)
        if pong.get("server_id") and pong.get("server_id") != req.server_id:
            reason = (f"reached {req.secondary_url} but it identifies as "
                      f"'{pong.get('server_id')}', not '{req.server_id}'")
        else:
            primary_to_secondary = True
    except Exception as e:  # noqa: BLE001
        reason = f"primary could not reach the secondary at {req.secondary_url}: {e}"

    ok = secondary_to_primary and primary_to_secondary
    if ok:
        db.db.federation_servers.update_one(
            {"server_id": req.server_id},
            {"$set": {"server_id": req.server_id, "url": req.secondary_url,
                      "enrolled_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    return {
        "ok": ok,
        "server_id": req.server_id,
        "directions": {
            "secondary_to_primary": secondary_to_primary,
            "primary_to_secondary": primary_to_secondary,
        },
        "reason": reason if not ok else None,
    }


@router.get("/leader")
def leader(_: str = Depends(verify_auth), cfg: Config = Depends(get_config), db: DBManager = Depends(get_db)):
    """Current cluster leader + lease state (the source of truth for who is primary)."""
    st = CL.lease_state(db.db)
    return {"node_id": cfg.server.id, "is_leader": st["valid"] and st["holder"] == cfg.server.id, "lease": st}


def _follow_lease(db: DBManager, leader_id: Optional[str]) -> None:
    """Mirror the lease holder into settings so the rest of the app + UI can read
    who the primary is without re-querying the lease."""
    db.db.settings.update_one({"_id": "app"}, {"$set": {"primary_node": leader_id}}, upsert=True)


class PromoteRequest(BaseModel):
    force: bool = False


@router.post("/promote")
def promote(
    req: PromoteRequest,
    actor: str = Depends(verify_auth),
    cfg: Config = Depends(get_config),
    db: DBManager = Depends(get_db),
):
    """Manually promote THIS node to primary. Guarded:
      - refuses if any reachable node reports a live leader (incl. the shared lease);
      - if some nodes are UNREACHABLE, refuses to silently promote — returns
        needs_force with a warning that the old primary can't be confirmed down;
      - only `force: true` (an explicit operator confirmation) seizes the lease
        despite unreachable nodes. Never auto-forces."""
    node_id = cfg.server.id
    ttl = cfg.federation.lease_ttl_seconds
    now = datetime.now(timezone.utc)

    # 1) Shared lease is the primary source of truth.
    st = CL.lease_state(db.db, now)
    if st["valid"] and st["holder"] and st["holder"] != node_id:
        return {"promoted": False, "leader": st["holder"],
                "reason": f"a live leader already holds the lease: {st['holder']}"}

    # 2) Defense-in-depth: probe every known peer directly over the mesh.
    foreign_leaders, unreachable = [], []
    for n in db.db.federation_servers.find({}, {"_id": 0, "server_id": 1, "url": 1}):
        if n.get("server_id") == node_id or not n.get("url"):
            continue
        try:
            pong = F.ping_node(n["url"])
            ld = pong.get("leader") or {}
            if ld.get("valid") and ld.get("holder") and ld.get("holder") != node_id:
                foreign_leaders.append(ld["holder"])
        except Exception:  # noqa: BLE001 — node unreachable
            unreachable.append(n["server_id"])

    if foreign_leaders:
        return {"promoted": False, "leader": sorted(set(foreign_leaders))[0],
                "reason": f"a reachable node reports a live leader: {sorted(set(foreign_leaders))}"}

    # 3) No live leader seen anywhere reachable.
    if unreachable and not req.force:
        return {
            "promoted": False, "needs_force": True, "unreachable": unreachable,
            "warning": ("cannot confirm the previous primary is down — these nodes are "
                        f"unreachable: {unreachable}. Forcing may create two primaries. "
                        "Re-submit with force=true only if you are certain the old primary is down."),
        }

    # 4) Acquire.
    if req.force:
        new = CL.force_acquire(db.db, node_id, ttl, now)
        _follow_lease(db, node_id)
        return {"promoted": True, "forced": True, "leader": node_id, "lease": new,
                "warning": "force-acquired despite unconfirmed nodes — verify no second primary is running."}
    ok = CL.try_acquire_or_renew(db.db, node_id, ttl, now)
    if ok:
        _follow_lease(db, node_id)
    return {"promoted": ok, "forced": False,
            "leader": node_id if ok else st.get("holder"),
            "reason": None if ok else "lost the acquire race to another node"}
