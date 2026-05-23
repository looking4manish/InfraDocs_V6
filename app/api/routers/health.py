"""Health endpoint — no auth required."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.dependencies import get_db
from app.core.db_manager import DBManager

router = APIRouter()


@router.get("/health")
def health(db: DBManager = Depends(get_db)):
    mongo_ok = True
    mongo_err = None
    try:
        db.client.admin.command("ping")
    except Exception as e:
        mongo_ok = False
        mongo_err = str(e)
    return {
        "status": "ok" if mongo_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mongo": {"ok": mongo_ok, "error": mongo_err},
    }
