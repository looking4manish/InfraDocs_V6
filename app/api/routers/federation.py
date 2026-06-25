"""Federation — a primary aggregates data pushed by secondaries.

Secondaries scan THEMSELVES and push (outbound, so it works behind NAT/CGNAT like
N150) to the primary's /api/federation/ingest, authenticated by a join token the
primary minted. The primary stores each server's data scoped by server_id, so its
dashboard shows every node. (Command dispatch primary->secondary is a later step;
this delivers the data plane.)
"""

import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.dependencies import get_db, verify_auth
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
