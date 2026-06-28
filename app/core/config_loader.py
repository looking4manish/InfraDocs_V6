"""Configuration loader — single-host (OCI) build."""

import os
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


class ServerConfig(BaseModel):
    id: str
    name: str
    api_port: int


class FeaturesConfig(BaseModel):
    scanner_enabled: bool = True
    api_enabled: bool = True
    frontend_enabled: bool = True


class MongoDBConfig(BaseModel):
    uri_env: str = "INFRADOCS_MONGO_URI"
    database: str

    @property
    def uri(self) -> str:
        value = os.environ.get(self.uri_env)
        if not value:
            raise RuntimeError(
                f"MongoDB URI not set: env var {self.uri_env} is missing. "
                f"Populate .env from .env.example."
            )
        return value


class PathsConfig(BaseModel):
    projects_root: str
    # Extra roots to HUNT for scattered projects (marker-based: docker-compose.yml/.git).
    scan_roots: Optional[List[str]] = None
    scan_depth: int = 2
    data_root: str
    logs_dir: str = "logs"
    artifacts_dir: str = "artifacts"


class ScanningConfig(BaseModel):
    schedule: str = "0 */6 * * *"
    timeout: int = 300
    enabled_scanners: List[str] = []


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    retention_days: int = 30


class AuthConfig(BaseModel):
    username: str
    password_env: str = "INFRADOCS_API_PASSWORD"
    dev_password: str = "changeme"


class FederationConfig(BaseModel):
    # Background leader-election renewer. OFF by default so installing this code on
    # a host changes nothing until a fleet is deliberately wired up.
    lease_enabled: bool = False
    # Lease validity window. If the leader misses every renewal for this long, the
    # lease expires and a peer can take over. renew_seconds MUST be << ttl_seconds
    # so a single dropped renewal (a brief blip) never triggers needless failover.
    lease_ttl_seconds: int = 15
    lease_renew_seconds: int = 5


class Config(BaseModel):
    server: ServerConfig
    features: FeaturesConfig
    mongodb: MongoDBConfig
    paths: PathsConfig
    scanning: ScanningConfig
    logging: LoggingConfig
    auth: AuthConfig
    federation: FederationConfig = FederationConfig()


def load_config(config_path: str = "config.yml") -> Config:
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Load .env sitting next to config.yml (project root) if present.
    env_file = config_file.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    with open(config_file, "r") as f:
        raw = yaml.safe_load(f)

    # Env overrides so the SAME image/config.yml deploys on any host via .env.
    _env_override(raw, "server", "id", "INFRADOCS_SERVER_ID")
    _env_override(raw, "server", "name", "INFRADOCS_SERVER_NAME")
    _env_override(raw, "paths", "projects_root", "INFRADOCS_PROJECTS_ROOT")
    _env_override(raw, "mongodb", "database", "INFRADOCS_DB")
    _env_override(raw, "auth", "username", "INFRADOCS_API_USERNAME")

    # Comma-separated extra roots to hunt for scattered projects.
    roots_env = os.environ.get("INFRADOCS_SCAN_ROOTS")
    if roots_env and isinstance(raw.get("paths"), dict):
        raw["paths"]["scan_roots"] = [r.strip() for r in roots_env.split(",") if r.strip()]

    return Config(**raw)


def _env_override(raw: dict, section: str, key: str, env: str) -> None:
    val = os.environ.get(env)
    if val and isinstance(raw.get(section), dict):
        raw[section][key] = val


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> Config:
    global _config
    _config = load_config()
    return _config
