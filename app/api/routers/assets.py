"""Assets endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import DESCENDING

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager

router = APIRouter()


@router.get("/")
def list_assets(
    category: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    query: dict = {}
    if category:
        query["category"] = category
    if project:
        query["project"] = project
    if status:
        query["status"] = status
    cursor = db.db.assets.find(query).sort("updated_at", DESCENDING).limit(limit)
    assets = []
    for a in cursor:
        a["_id"] = str(a["_id"])
        assets.append(a)
    return {"count": len(assets), "assets": assets}


@router.get("/categories")
def list_categories(
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    rows = list(db.db.assets.aggregate(pipeline))
    return {
        "categories": [
            {"category": r["_id"], "count": r["count"]} for r in rows if r["_id"]
        ]
    }


@router.get("/{asset_id}")
def get_asset(
    asset_id: str,
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    asset = db.db.assets.find_one({"asset_id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="asset not found")
    asset["_id"] = str(asset["_id"])
    return asset
