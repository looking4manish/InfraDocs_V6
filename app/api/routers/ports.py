"""Ports endpoints — registry view + live probe (Phase 7B)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager
from app.ports_registry import probe as live_probe

router = APIRouter()


@router.get("/")
def list_ports(
    state: Optional[str] = Query(None, description="in_use | declared"),
    project: Optional[str] = Query(None, description="filter by owner project name"),
    port_min: Optional[int] = Query(None, ge=1, le=65535),
    port_max: Optional[int] = Query(None, ge=1, le=65535),
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    rows = db.get_ports(
        state=state, project=project, port_min=port_min, port_max=port_max
    )
    return {"count": len(rows), "ports": rows}


@router.get("/summary")
def ports_summary(
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    """Counts by state + by owner project."""
    pipeline_state = [
        {"$group": {"_id": "$state", "count": {"$sum": 1}}},
    ]
    pipeline_owner = [
        {"$group": {"_id": "$owner_project", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    by_state = {r["_id"]: r["count"] for r in db.db.ports.aggregate(pipeline_state)}
    by_owner = [
        {"project": r["_id"], "count": r["count"]}
        for r in db.db.ports.aggregate(pipeline_owner)
    ]
    return {
        "total": db.db.ports.count_documents({}),
        "by_state": by_state,
        "by_owner": by_owner,
    }


@router.get("/probe")
def probe_ports(
    range: str = Query(..., description="port range, e.g. 8000-9000 or 8080"),
    proto: str = Query("tcp", regex="^(tcp|udp)$"),
    _: str = Depends(verify_auth),
):
    """Live `ss` snapshot of the requested port range. NOT persisted."""
    if "-" in range:
        try:
            start_s, end_s = range.split("-", 1)
            start, end = int(start_s), int(end_s)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad range")
    else:
        try:
            start = end = int(range)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad range")
    if end - start > 5000:
        raise HTTPException(
            status_code=400,
            detail="range too wide; cap is 5000 ports per probe",
        )
    try:
        rows = live_probe(start, end, proto=proto)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "range": [start, end],
        "protocol": proto,
        "count": len(rows),
        "in_use_count": sum(1 for r in rows if r["state"] == "in_use"),
        "ports": rows,
    }
