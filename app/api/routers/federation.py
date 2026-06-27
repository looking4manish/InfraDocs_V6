"""Federation — a primary aggregates data pushed by secondaries.

Secondaries scan THEMSELVES and push (outbound, so it works behind NAT/CGNAT like
N150) to the primary's /api/federation/ingest, authenticated by a join token the
primary minted. The primary stores each server's data scoped by server_id, so its
dashboard shows every node. (Command dispatch primary->secondary is a later step;
this delivers the data plane.)
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from pymongo import ReturnDocument

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager

router = APIRouter()

# Mirror app.actions' self-protection without importing it at module load
# (that module pulls in the docker SDK; the primary has it, but keep the
# coupling lazy/cheap — the prefix list is the only thing we need here).
SELF_PROTECT_PREFIXES = ("infradocs-v6-",)


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
# Command dispatch (primary -> secondary) — Model A: queue + outbound poll.
#
# A secondary sits behind NAT, so the primary can never reach in. Instead the
# primary ENQUEUES a command; the secondary PULLS pending commands on its next
# poll (an outbound request, like the data-plane push), runs each through the
# SAME guarded actions dispatcher (app.actions.dispatch — so self-protection and
# the allow-list apply identically), then PUSHES the result back. Every step is
# recorded in actions_log on the primary so the fleet has one audit trail.
# ===========================================================================


def _is_self_protected(name: str) -> bool:
    return any((name or "").startswith(p) for p in SELF_PROTECT_PREFIXES)

# How long a claimed-but-unreported command may sit before the reaper closes it.
# A dispatched command is one guarded action (start/stop/restart/logs); if the
# secondary hasn't reported in this window it's dead (host down, poll cycle died,
# network dropped), not slow. Mark it 'expired' and write the closing audit entry
# — never DELETE, so the actions_log trail stays intact.
COMMAND_EXPIRY_SECONDS = 15 * 60


def reap_stale_commands(db: DBManager) -> int:
    """Close out commands claimed (status='dispatched') but never reported within
    COMMAND_EXPIRY_SECONDS. Returns the number reaped. Idempotent; safe to call
    on every /commands read. Only touches 'dispatched' rows with a dispatched_at —
    a 'pending' row that's merely old just hasn't been polled yet and is left alone.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=COMMAND_EXPIRY_SECONDS)
    reaped = 0
    while True:
        cmd = db.db.federation_commands.find_one_and_update(
            {"status": "dispatched", "dispatched_at": {"$lt": cutoff}},
            {"$set": {
                "status": "expired",
                "completed_at": datetime.now(timezone.utc),
                "result": {
                    "status": "expired",
                    "stdout": "",
                    "stderr": "",
                    "return_code": None,
                    "duration_ms": 0,
                    "refused_reason": "no result reported before expiry",
                },
            }},
            return_document=ReturnDocument.AFTER,
        )
        if not cmd:
            break
        asset = cmd.get("asset", {})
        db.record_action({
            "actor": cmd.get("created_by"),
            "server_id": cmd.get("server_id"),
            "asset_id": asset.get("asset_id"),
            "asset_name": asset.get("name"),
            "category": asset.get("category"),
            "project": asset.get("project"),
            "action": cmd.get("action"),
            "args": cmd.get("args", {}),
            "status": "expired",
            "refused_reason": "no result reported before expiry",
            "command_id": cmd.get("command_id"),
            "origin": "federation",
        })
        reaped += 1
    return reaped

class DispatchRequest(BaseModel):
    server_id: str
    asset_id: str
    action: str
    args: Dict[str, Any] = {}


@router.post("/commands")
def create_command(
    req: DispatchRequest,
    actor: str = Depends(verify_auth),
    db: DBManager = Depends(get_db),
):
    """Primary: enqueue an action for a secondary to execute on its next poll."""
    if not db.db.federation_servers.find_one({"server_id": req.server_id}):
        raise HTTPException(status_code=404, detail=f"unknown server: {req.server_id}")

    asset = db.db.assets.find_one({"asset_id": req.asset_id, "server_id": req.server_id})
    if not asset:
        raise HTTPException(
            status_code=404,
            detail=f"asset '{req.asset_id}' not found on server '{req.server_id}'",
        )

    name = asset.get("name", "")
    # Refuse up front (the secondary's dispatcher would refuse too, but failing
    # fast here gives the operator the 409 immediately and never queues it).
    if _is_self_protected(name):
        raise HTTPException(
            status_code=409,
            detail=f"refusing to dispatch to protected asset: {name}",
        )

    # Embed just what the remote dispatcher needs (category/name/metadata).
    payload_asset = {
        "category": asset.get("category"),
        "asset_id": asset.get("asset_id"),
        "name": asset.get("name"),
        "project": asset.get("project"),
        "metadata": asset.get("metadata", {}),
    }
    command_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    db.db.federation_commands.insert_one({
        "command_id": command_id,
        "server_id": req.server_id,
        "asset": payload_asset,
        "action": req.action,
        "args": req.args,
        "status": "pending",
        "created_at": now,
        "created_by": actor,
    })
    # Audit the dispatch the moment it's queued (status flips on completion).
    db.record_action({
        "actor": actor,
        "server_id": req.server_id,
        "asset_id": payload_asset["asset_id"],
        "asset_name": payload_asset["name"],
        "category": payload_asset["category"],
        "project": payload_asset["project"],
        "action": req.action,
        "args": req.args,
        "status": "pending",
        "command_id": command_id,
        "origin": "federation",
    })
    return {"command_id": command_id, "server_id": req.server_id, "status": "pending"}


@router.get("/commands")
def list_commands(
    server_id: Optional[str] = None,
    limit: int = 50,
    _: str = Depends(verify_auth),
    db: DBManager = Depends(get_db),
):
    """Primary: list recent dispatched commands (drives the Servers-lens panel)."""
    reap_stale_commands(db)
    q = {"server_id": server_id} if server_id else {}
    rows = list(
        db.db.federation_commands.find(q, {"_id": 0})
        .sort("created_at", -1)
        .limit(min(max(limit, 1), 200))
    )
    return {"commands": rows, "count": len(rows)}


class PendingRequest(BaseModel):
    server_id: str


@router.post("/commands/pending")
def claim_pending(
    req: PendingRequest,
    x_join_token: Optional[str] = Header(None),
    db: DBManager = Depends(get_db),
):
    """Secondary -> primary (outbound): atomically claim this server's pending
    commands, flipping them to 'dispatched' so a re-poll can't double-run them."""
    if not _valid_token(db, req.server_id, x_join_token):
        raise HTTPException(status_code=401, detail="invalid or missing join token")
    now = datetime.now(timezone.utc)
    claimed = []
    while True:
        doc = db.db.federation_commands.find_one_and_update(
            {"server_id": req.server_id, "status": "pending"},
            {"$set": {"status": "dispatched", "dispatched_at": now}},
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        if not doc:
            break
        claimed.append(doc)
    return {"commands": claimed, "count": len(claimed)}


class ResultRequest(BaseModel):
    server_id: str
    status: str  # success | failed | refused
    stdout: str = ""
    stderr: str = ""
    return_code: Optional[int] = None
    duration_ms: int = 0
    refused_reason: Optional[str] = None


@router.post("/commands/{command_id}/result")
def report_result(
    command_id: str,
    req: ResultRequest,
    x_join_token: Optional[str] = Header(None),
    db: DBManager = Depends(get_db),
):
    """Secondary -> primary (outbound): report a command's outcome. The primary
    closes out the command and writes the final, audited actions_log entry."""
    if not _valid_token(db, req.server_id, x_join_token):
        raise HTTPException(status_code=401, detail="invalid or missing join token")
    cmd = db.db.federation_commands.find_one({"command_id": command_id})
    if not cmd:
        raise HTTPException(status_code=404, detail="unknown command")
    if cmd.get("server_id") != req.server_id:
        # A token is scoped to one server; it can't close another server's command.
        raise HTTPException(status_code=403, detail="token not scoped to this command")

    result = {
        "status": req.status,
        "stdout": (req.stdout or "")[-4000:],
        "stderr": (req.stderr or "")[-4000:],
        "return_code": req.return_code,
        "duration_ms": req.duration_ms,
        "refused_reason": req.refused_reason,
    }
    db.db.federation_commands.update_one(
        {"command_id": command_id},
        {"$set": {"status": req.status, "completed_at": datetime.now(timezone.utc), "result": result}},
    )
    asset = cmd.get("asset", {})
    db.record_action({
        "actor": cmd.get("created_by"),
        "server_id": req.server_id,
        "asset_id": asset.get("asset_id"),
        "asset_name": asset.get("name"),
        "category": asset.get("category"),
        "project": asset.get("project"),
        "action": cmd.get("action"),
        "args": cmd.get("args", {}),
        "status": req.status,
        "return_code": req.return_code,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "duration_ms": req.duration_ms,
        "refused_reason": req.refused_reason,
        "command_id": command_id,
        "origin": "federation",
    })
    return {"ok": True, "command_id": command_id, "status": req.status}
