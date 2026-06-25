"""InfraDocs V6 API entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from project root before any other module touches os.environ.
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)

from app import auth as _auth  # noqa: E402
from app.api.dependencies import get_config, get_db  # noqa: E402
from app.api.routers import (  # noqa: E402
    actions, applications, assets, auth, health, ports, projects, scans, setup, storage,
)
from app.core.logger import setup_logger  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logger("api", log_file="logs/api.log", level="INFO")
    cfg = get_config()
    db = get_db()
    db.create_indexes()
    _auth.seed_default_admin(db, cfg.auth.username)
    logger.info(f"API started for server '{cfg.server.id}'")
    try:
        yield
    finally:
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
