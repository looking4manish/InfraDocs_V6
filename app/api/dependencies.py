"""FastAPI dependencies: config, DB connection, basic-auth."""

import os
import secrets
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config_loader import Config, load_config
from app.core.db_manager import DBManager


_basic = HTTPBasic()


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config()


@lru_cache(maxsize=1)
def get_db() -> DBManager:
    cfg = get_config()
    return DBManager(uri=cfg.mongodb.uri, database=cfg.mongodb.database)


def verify_auth(
    credentials: HTTPBasicCredentials = Depends(_basic),
    cfg: Config = Depends(get_config),
) -> str:
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
