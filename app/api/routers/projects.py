"""Projects endpoints — aggregations over the assets collection."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager

router = APIRouter()


def _health_score_from_assets(assets) -> int:
    """Crude health score: average of per-asset health where derivable."""
    if not assets:
        return 100
    scores = []
    for a in assets:
        hi = a.get("health_indicators") or {}
        if a["category"].startswith("storage_"):
            pct = hi.get("usage_percent", 0)
            scores.append(max(0, 100 - pct))
        elif a["category"] == "docker_container":
            if a.get("status") == "running":
                scores.append(95 if hi.get("restarts", 0) == 0 else 70)
            else:
                scores.append(40)
        elif a["category"] in {"systemd_service", "systemd_timer"}:
            scores.append(95 if a.get("status") == "active" else 50)
        else:
            scores.append(90)
    return round(sum(scores) / len(scores))


@router.get("/list")
def list_projects(
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    pipeline = [
        {
            "$group": {
                "_id": "$project",
                "asset_count": {"$sum": 1},
                "categories": {"$addToSet": "$category"},
                "assets": {"$push": "$$ROOT"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    rows = list(db.db.assets.aggregate(pipeline))
    # Full root path per project (discovered + tagged at scan time).
    root_paths = {
        a["name"]: a.get("root_path")
        for a in db.db.applications.find(
            {"root_path": {"$exists": True}}, {"name": 1, "root_path": 1}
        )
    }
    out = []
    for r in rows:
        name = r["_id"] or "System"
        by_cat: dict = {}
        for a in r["assets"]:
            by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
        score = _health_score_from_assets(r["assets"])
        out.append(
            {
                "name": name,
                "asset_count": r["asset_count"],
                "categories": by_cat,
                "health_score": score,
                "is_healthy": score >= 80,
                "root_path": root_paths.get(name),
            }
        )
    return {"count": len(out), "projects": out}


@router.get("/{project_name}")
def project_detail(
    project_name: str,
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    assets = list(db.db.assets.find({"project": project_name}))
    if not assets:
        raise HTTPException(status_code=404, detail="project has no assets")
    for a in assets:
        a["_id"] = str(a["_id"])
    by_cat: dict = {}
    for a in assets:
        by_cat[a["category"]] = by_cat.get(a["category"], 0) + 1
    return {
        "name": project_name,
        "asset_count": len(assets),
        "categories": by_cat,
        "health_score": _health_score_from_assets(assets),
        "assets": assets,
    }
