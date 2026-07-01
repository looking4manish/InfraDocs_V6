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


# Sensible full-disk defaults so discovery covers "anywhere an app can live",
# not just one home-relative folder — used when config.yml omits these keys.
DEFAULT_DIRECT_ROOTS: List[str] = ["/opt", "/srv", "/var/www"]
DEFAULT_SCAN_ROOTS: List[str] = ["/opt", "/srv", "/usr/local", "/var/www", "/home", "/etc"]


class PathsConfig(BaseModel):
    projects_root: str
    # Extra roots whose DIRECT children are each an application (install layout:
    # /opt/<app>, /srv/<app>, /var/www/<site>). Direct discovery, like projects_root.
    direct_roots: Optional[List[str]] = None
    # Broader roots to recursively HUNT for scattered projects
    # (marker-based: docker-compose.yml / .git). Marker-only so /home/<user> and
    # /etc/<config> don't each become an "app".
    scan_roots: Optional[List[str]] = None
    scan_depth: int = 2
    # Wall-clock cap (seconds) for the whole filesystem discovery pass so a
    # full-disk scan can never hang the pipeline. <=0 disables the cap.
    scan_timeout_seconds: int = 120
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
    # Gossip cluster + failover. OFF by default so installing this code on a host
    # changes nothing until a real multi-node fleet is deliberately wired up.
    cluster_enabled: bool = False
    # Every node health-checks every peer this often. A peer unheard-from for
    # ~MISS_ROUNDS intervals (unreachable_after) is treated as down; the primary is
    # considered lost after the same window, which then (in a majority) triggers an
    # election. Loose enough that a single missed round never causes a failover.
    health_interval_seconds: int = 10
    unreachable_after_seconds: int = 30  # 3 missed rounds


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

    # Comma-separated root overrides (env wins). Marker-hunt roots and direct
    # (one-folder-per-app) roots are configured independently.
    paths = raw.get("paths")
    if isinstance(paths, dict):
        roots_env = os.environ.get("INFRADOCS_SCAN_ROOTS")
        if roots_env is not None:
            paths["scan_roots"] = [r.strip() for r in roots_env.split(",") if r.strip()]
        direct_env = os.environ.get("INFRADOCS_DIRECT_ROOTS")
        if direct_env is not None:
            paths["direct_roots"] = [r.strip() for r in direct_env.split(",") if r.strip()]
        # Full-disk defaults when neither config.yml nor env supplied a value, so
        # discovery can never silently collapse back to the single projects_root.
        if paths.get("scan_roots") is None:
            paths["scan_roots"] = list(DEFAULT_SCAN_ROOTS)
        if paths.get("direct_roots") is None:
            paths["direct_roots"] = list(DEFAULT_DIRECT_ROOTS)

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
