"""AI layer endpoints — Tier 2 (label unknown services) + Tier 3 (fleet insights).

All optional: every route degrades gracefully when no AI endpoint is configured.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends

from app import ai
from app.api.dependencies import get_config, get_db, verify_auth
from app.core.config_loader import Config
from app.core.db_manager import DBManager
from app.core.recognize import recognize

router = APIRouter()

_SKIP_PROCS = {"unknown", "docker-proxy", "systemd", "sshd", "rpcbind", ""}


def _signature(image: Optional[str], process: Optional[str], port) -> Optional[str]:
    if image:
        return "image:" + image
    if process and process not in _SKIP_PROCS:
        return "proc:" + process
    if port:
        return f"port:{port}"
    return None


@router.get("/status")
def status(db: DBManager = Depends(get_db), _: str = Depends(verify_auth)):
    cfg = ai.config(db)
    return {
        "enabled": bool(cfg["endpoint"]),
        "model": cfg["model"] if cfg["endpoint"] else None,
        "labeled": db.db.ai_labels.count_documents({}),
        "has_insights": bool((db.db.settings.find_one({"_id": "app"}) or {}).get("ai_insights")),
    }


@router.get("/labels")
def labels(db: DBManager = Depends(get_db), _: str = Depends(verify_auth)):
    rows = list(db.db.ai_labels.find({}, {"_id": 1, "label": 1, "kind": 1, "purpose": 1}))
    return {"count": len(rows), "labels": rows}


def _candidates(db: DBManager, server: Optional[str]):
    """Unrecognized services worth an LLM label: containers (by image) + ports (by process)."""
    q = {"server_id": server} if server else {}
    seen, out = set(), []
    for c in db.db.assets.find({**q, "category": "docker_container"}):
        m = c.get("metadata", {}) or {}
        image = m.get("image") or m.get("image_name")
        if not image or recognize(image=image):
            continue
        sig = _signature(image, None, None)
        if sig and sig not in seen:
            seen.add(sig)
            out.append((sig, {"kind_hint": "docker container", "image": image,
                              "name": c.get("name"), "ports": m.get("host_ports"),
                              "project": c.get("project")}))
    for p in db.db.assets.find({**q, "category": "network_port"}):
        m = p.get("metadata", {}) or {}
        proc, port = m.get("process"), m.get("port")
        if proc in _SKIP_PROCS or recognize(port=port, process=proc):
            continue
        sig = _signature(None, proc, port)
        if sig and sig not in seen:
            seen.add(sig)
            out.append((sig, {"kind_hint": "listening port", "process": proc,
                              "port": port, "project": p.get("project")}))
    return out


def _run_enrich(cfg: Config, server: Optional[str], limit: int):
    db = DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)
    try:
        for sig, evidence in _candidates(db, server)[:limit]:
            if db.db.ai_labels.find_one({"_id": sig}):
                continue  # cached — one-time cost per distinct service
            res = ai.label_service(db, evidence)
            if res:
                db.db.ai_labels.update_one(
                    {"_id": sig},
                    {"$set": {**res, "evidence": evidence,
                              "created_at": datetime.now(timezone.utc)}},
                    upsert=True,
                )
    finally:
        db.close()


@router.post("/enrich")
def enrich(background: BackgroundTasks, server: Optional[str] = None, limit: int = 40,
           db: DBManager = Depends(get_db), cfg: Config = Depends(get_config),
           _: str = Depends(verify_auth)):
    if not ai.enabled(db):
        return {"enabled": False, "scheduled": 0,
                "message": "No AI endpoint configured (set it in the wizard or .env)."}
    pending = [s for s, _e in _candidates(db, server)
               if not db.db.ai_labels.find_one({"_id": s})]
    background.add_task(_run_enrich, cfg, server, limit)
    return {"enabled": True, "scheduled": min(len(pending), limit), "pending": len(pending)}


@router.post("/insights")
def insights(server: Optional[str] = None, db: DBManager = Depends(get_db),
             _: str = Depends(verify_auth)):
    if not ai.enabled(db):
        return {"enabled": False, "message": "No AI endpoint configured."}
    inv = _inventory(db, server)
    result = ai.fleet_insights(db, inv)
    if result:
        db.db.settings.update_one({"_id": "app"}, {"$set": {
            "ai_insights": result, "ai_insights_at": datetime.now(timezone.utc),
        }}, upsert=True)
    return {"enabled": True, "insights": result}


@router.get("/insights")
def get_insights(db: DBManager = Depends(get_db), _: str = Depends(verify_auth)):
    s = db.db.settings.find_one({"_id": "app"}) or {}
    return {"insights": s.get("ai_insights"), "generated_at": s.get("ai_insights_at")}


def _inventory(db: DBManager, server: Optional[str]) -> dict:
    """A compact, non-sensitive snapshot for the insights prompt."""
    q = {"server_id": server} if server else {}
    apps = list(db.db.applications.find(q, {"name": 1, "type": 1, "internet_exposed": 1,
                                            "exposure": 1, "server_id": 1, "_id": 0}))
    servers = list(db.db.federation_servers.find({}, {"_id": 0}))
    ports = [{"port": (a.get("metadata") or {}).get("port"),
              "process": (a.get("metadata") or {}).get("process"),
              "server": a.get("server_id")}
             for a in db.db.assets.find({**q, "category": "network_port"})]
    return {"applications": apps[:120], "servers": servers, "listening_ports": ports[:120]}
