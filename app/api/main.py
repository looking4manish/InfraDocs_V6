"""InfraDocs V6 API entry point."""

import asyncio  # noqa: E402
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from project root before any other module touches os.environ.
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)

from app import auth as _auth  # noqa: E402
from app import cluster_lease as _lease  # noqa: E402
from app.api.dependencies import get_config, get_db  # noqa: E402
from app.api.routers import (  # noqa: E402
    actions, ai, applications, assets, auth, endpoints, federation, health, ports, projects, scans, setup, storage,
)
from app.core.logger import setup_logger  # noqa: E402


async def _lease_renewer(cfg, db, logger):
    """Every renew_seconds, atomically try to hold the lease; mirror the holder into
    settings.primary_node so 'who is primary' follows the lease. Renewal failing
    just means a peer is leader — we stay a follower and keep trying. Blocking pymongo
    calls run in a thread so the event loop is never stalled."""
    node_id, ttl, renew = cfg.server.id, cfg.federation.lease_ttl_seconds, cfg.federation.lease_renew_seconds
    while True:
        try:
            held = await asyncio.to_thread(_lease.try_acquire_or_renew, db.db, node_id, ttl)
            st = await asyncio.to_thread(_lease.lease_state, db.db)
            await asyncio.to_thread(
                lambda: db.db.settings.update_one(
                    {"_id": "app"}, {"$set": {"primary_node": st.get("holder")}}, upsert=True
                )
            )
            if held:
                logger.debug("lease renewed by %s", node_id)
        except Exception as e:  # noqa: BLE001 — never let a transient DB blip kill the loop
            logger.warning("lease renew tick failed: %s", e)
        await asyncio.sleep(renew)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logger("api", log_file="logs/api.log", level="INFO")
    cfg = get_config()
    db = get_db()
    db.create_indexes()
    _auth.seed_default_admin(db, cfg.auth.username)
    logger.info(f"API started for server '{cfg.server.id}'")
    renewer = None
    if cfg.federation.lease_enabled:
        renewer = asyncio.create_task(_lease_renewer(cfg, db, logger))
        logger.info("leader-election renewer started (ttl=%ss renew=%ss)",
                    cfg.federation.lease_ttl_seconds, cfg.federation.lease_renew_seconds)
    try:
        yield
    finally:
        if renewer:
            renewer.cancel()
        db.close()
        logger.info("API shutdown complete")


app = FastAPI(
    title="InfraDocs V6 API",
    version="0.1.0",
    description="Single-host (OCI) infrastructure documentation API.",
    lifespan=lifespan,
)

# CORS — Phase 4 frontend runs separately (dev) and via nginx proxy (prod).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(setup.router, prefix="/api/setup", tags=["setup"])
app.include_router(endpoints.router, prefix="/api/endpoints", tags=["endpoints"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(federation.router, prefix="/api/federation", tags=["federation"])
app.include_router(assets.router, prefix="/api/assets", tags=["assets"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(ports.router, prefix="/api/ports", tags=["ports"])
app.include_router(storage.router, prefix="/api/storage", tags=["storage"])
app.include_router(scans.router, prefix="/api/scans", tags=["scans"])
# actions router declares its own /assets/{id}/action and /applications/{name}/action
# paths plus /actions/* — mount it at /api so all three sit at the right URLs.
app.include_router(actions.router, prefix="/api", tags=["actions"])


@app.get("/")
def root():
    return {"name": "InfraDocs V6", "version": "0.1.0"}
