"""FastAPI dependencies: config, DB connection, basic-auth."""

import os
import secrets
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config_loader import Config, load_config
from app.core.db_manager import DBManager


# auto_error=False so verify_auth() can decide what to do when no header
# is present — needed for the INFRADOCS_AUTH_DISABLED bypass below.
_basic = HTTPBasic(auto_error=False)


def _auth_disabled() -> bool:
    return os.environ.get("INFRADOCS_AUTH_DISABLED", "").lower() in (
        "1", "true", "yes", "on",
    )


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()


@lru_cache(maxsize=1)
def get_db() -> DBManager:
    cfg = get_config()
    return DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)


def verify_auth(
    credentials: Optional[HTTPBasicCredentials] = Depends(_basic),
    cfg: Config = Depends(get_config),
) -> str:
    # Open-house mode: set INFRADOCS_AUTH_DISABLED=1 in .env to bypass auth.
    # Any audit-log actor is recorded as the client-supplied username (or
    # "anonymous" if no header at all), so actions are still attributable
    # to whoever the client claimed to be.
    if _auth_disabled():
        return credentials.username if credentials else "anonymous"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    expected_password = os.environ.get(cfg.auth.password_env) or cfg.auth.dev_password

    # constant-time comparison
    user_ok = secrets.compare_digest(credentials.username, cfg.auth.username)
    pass_ok = secrets.compare_digest(credentials.password, expected_password)

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
