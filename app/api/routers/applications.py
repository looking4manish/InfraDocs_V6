"""Applications endpoints — the application-centric view."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_db, verify_auth
from app.blast_radius import compute_blast_radius
from app.core.db_manager import DBManager

router = APIRouter()


@router.get("/list")
def list_applications(
    internet_exposed: bool | None = Query(None),
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    query = {}
    if internet_exposed is not None:
        query["internet_exposed"] = internet_exposed
    apps = list(db.db.applications.find(query).sort("name", 1))
    for a in apps:
        a["_id"] = str(a["_id"])
    return {"count": len(apps), "applications": apps}


@router.get("/{name}/blast-radius")
def application_blast_radius(
    name: str,
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    """Read-only teardown preview: every asset a kill would touch, with
    data-loss and shared (must-not-remove) flags. Changes nothing."""
    app = db.get_application(name)
    if not app:
        raise HTTPException(status_code=404, detail="application not found")
    all_apps = list(db.db.applications.find({}))
    return compute_blast_radius(app, all_apps)


@router.get("/{name}")
def get_application(
    name: str,
    db: DBManager = Depends(get_db),
    _: str = Depends(verify_auth),
):
    app = db.get_application(name)
    if not app:
        raise HTTPException(status_code=404, detail="application not found")
    return app
