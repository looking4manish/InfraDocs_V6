"""Storage endpoints — registry view (Phase 7C)."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager

router = APIRouter()


@router.get("/")
def list_storage(
    kind: Optional[str] = Query(None, description="mount | docker_volume | project_tree | bind_mount"),
    project: Optional[str] = Query(None, description="filter by owner project name"),
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    rows = db.get_storage(kind=kind, project=project)
    return {"count": len(rows), "storage": rows}


@router.get("/summary")
def storage_summary(
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    pipeline_kind = [
        {"$group": {
            "_id": "$kind",
            "count": {"$sum": 1},
            "size_bytes": {"$sum": "$size_bytes"},
        }},
        {"$sort": {"size_bytes": -1}},
    ]
    pipeline_owner = [
        {"$group": {
            "_id": "$owner_project",
            "count": {"$sum": 1},
            "size_bytes": {"$sum": "$size_bytes"},
        }},
        {"$sort": {"size_bytes": -1}},
    ]
    by_kind = [
        {"kind": r["_id"], "count": r["count"], "size_bytes": r["size_bytes"]}
        for r in db.db.storage.aggregate(pipeline_kind)
    ]
    by_owner = [
        {"project": r["_id"], "count": r["count"], "size_bytes": r["size_bytes"]}
        for r in db.db.storage.aggregate(pipeline_owner)
    ]
    return {
        "total": db.db.storage.count_documents({}),
        "by_kind": by_kind,
        "by_owner": by_owner,
    }
