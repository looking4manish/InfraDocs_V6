"""Phase 7 — API-level tests for /api/ports/* and /api/storage/*.

Mirrors the Phase 3 pattern: dependency-override the DB to point at a
throwaway test database, seed it directly, hit the endpoints.
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent import audit_ownership
from app.api import dependencies as api_deps
from app.api.main import app
from app.core.config_loader import load_config
from app.core.db_manager import DBManager


PHASE7_TEST_DB = "infradocs_phase7_test"


def _resolve_auth():
    _cfg = load_config(str(ROOT / "config.yml"))
    return (
        _cfg.auth.username,
        os.environ.get(_cfg.auth.password_env) or _cfg.auth.dev_password,
    )


AUTH = _resolve_auth()


@pytest.fixture(scope="module")
def cfg():
    return load_config(str(ROOT / "config.yml"))


@pytest.fixture
def client(cfg):
    if not os.environ.get(cfg.mongodb.uri_env):
        pytest.skip("MongoDB URI not configured")
    test_db = DBManager(uri=cfg.mongodb.uri, database=PHASE7_TEST_DB)
    test_db.create_indexes()

    # Seed ports
    sample_ports = [
        {
            "port_id": "oci:port:tcp:8004",
            "port": 8004,
            "protocol": "tcp",
            "state": "in_use",
            "process": "python",
            "pid": 1,
            "owner_project": "InfraDocs_V6",
            "owner_app_id": "oci:app:InfraDocs_V6",
            "evidence_sources": [{"kind": "listening", "source": "python"}],
        },
        {
            "port_id": "oci:port:tcp:80",
            "port": 80,
            "protocol": "tcp",
            "state": "in_use",
            "owner_project": "System",
            "owner_app_id": "oci:app:System",
            "evidence_sources": [{"kind": "listening", "source": "nginx"}],
        },
        {
            "port_id": "oci:port:tcp:9999",
            "port": 9999,
            "protocol": "tcp",
            "state": "declared",
            "owner_project": "openwebui",
            "owner_app_id": "oci:app:openwebui",
            "evidence_sources": [{"kind": "container", "source": "openwebui:9999/tcp"}],
        },
    ]
    test_db.replace_ports(sample_ports)

    # Seed storage
    sample_storage = [
        {
            "storage_id": "oci:storage:mount:/",
            "kind": "mount",
            "name": "/",
            "path": "/",
            "owner_project": "System",
            "owner_app_id": "oci:app:System",
            "size_bytes": 100_000_000_000,
            "total_bytes": 200_000_000_000,
            "used_bytes": 100_000_000_000,
            "free_bytes": 100_000_000_000,
            "fstype": "ext4",
            "device": "/dev/sda1",
            "usage_percent": 50,
            "evidence_sources": [{"kind": "df", "source": "/"}],
        },
        {
            "storage_id": "oci:storage:tree:openwebui",
            "kind": "project_tree",
            "name": "openwebui",
            "path": "/home/msinha/projects/openwebui",
            "owner_project": "openwebui",
            "owner_app_id": "oci:app:openwebui",
            "size_bytes": 4_000_000_000,
            "evidence_sources": [{"kind": "du", "source": "/home/msinha/projects/openwebui"}],
        },
        {
            "storage_id": "oci:storage:volume:openwebui_data",
            "kind": "docker_volume",
            "name": "openwebui_data",
            "path": "/var/lib/docker/volumes/openwebui_data/_data",
            "owner_project": "openwebui",
            "owner_app_id": "oci:app:openwebui",
            "size_bytes": 500_000_000,
            "evidence_sources": [{"kind": "docker_volume", "source": "openwebui_data"}],
        },
    ]
    test_db.replace_storage(sample_storage)

    app.dependency_overrides[api_deps.get_db] = lambda: test_db
    app.dependency_overrides[api_deps.get_config] = lambda: cfg

    yield TestClient(app)

    app.dependency_overrides.clear()
    test_db.client.drop_database(PHASE7_TEST_DB)
    test_db.close()


# ----------------------------- ports endpoints ------------------------------


def test_ports_list_all(client):
    r = client.get("/api/ports/", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3


def test_ports_list_filter_state(client):
    r = client.get("/api/ports/?state=in_use", auth=AUTH)
    assert r.json()["count"] == 2


def test_ports_list_filter_project(client):
    r = client.get("/api/ports/?project=openwebui", auth=AUTH)
    body = r.json()
    assert body["count"] == 1
    assert body["ports"][0]["port"] == 9999


def test_ports_list_filter_range(client):
    r = client.get("/api/ports/?port_min=8000&port_max=8100", auth=AUTH)
    body = r.json()
    assert body["count"] == 1
    assert body["ports"][0]["port"] == 8004


def test_ports_summary(client):
    r = client.get("/api/ports/summary", auth=AUTH)
    body = r.json()
    assert body["total"] == 3
    assert body["by_state"] == {"in_use": 2, "declared": 1}
    owners = {row["project"]: row["count"] for row in body["by_owner"]}
    assert owners == {"InfraDocs_V6": 1, "System": 1, "openwebui": 1}


def test_ports_probe_invalid_range(client):
    r = client.get("/api/ports/probe?range=bogus", auth=AUTH)
    assert r.status_code == 400


def test_ports_probe_too_wide(client):
    r = client.get("/api/ports/probe?range=1-65535", auth=AUTH)
    assert r.status_code == 400


def test_ports_probe_returns_range(client):
    r = client.get("/api/ports/probe?range=9000-9005", auth=AUTH)
    body = r.json()
    assert body["range"] == [9000, 9005]
    assert body["count"] == 6
    assert all(p["port"] in range(9000, 9006) for p in body["ports"])


def test_ports_auth_required(client):
    r = client.get("/api/ports/")
    assert r.status_code == 401


# ----------------------------- storage endpoints ----------------------------


def test_storage_list_all(client):
    r = client.get("/api/storage/", auth=AUTH)
    assert r.json()["count"] == 3


def test_storage_list_filter_kind(client):
    r = client.get("/api/storage/?kind=mount", auth=AUTH)
    assert r.json()["count"] == 1
    assert r.json()["storage"][0]["name"] == "/"


def test_storage_list_filter_project(client):
    r = client.get("/api/storage/?project=openwebui", auth=AUTH)
    body = r.json()
    assert body["count"] == 2
    kinds = {s["kind"] for s in body["storage"]}
    assert kinds == {"project_tree", "docker_volume"}


def test_storage_summary(client):
    r = client.get("/api/storage/summary", auth=AUTH)
    body = r.json()
    assert body["total"] == 3
    kinds = {row["kind"]: row["count"] for row in body["by_kind"]}
    assert kinds == {"mount": 1, "project_tree": 1, "docker_volume": 1}
    owners = {row["project"]: row["size_bytes"] for row in body["by_owner"]}
    assert owners["openwebui"] == 4_500_000_000  # tree 4G + volume 500M
    assert owners["System"] == 100_000_000_000


def test_storage_auth_required(client):
    r = client.get("/api/storage/")
    assert r.status_code == 401


# ----------------------------- ownership audit ------------------------------


def test_audit_ownership_clean_pass():
    """Every asset has a valid project → ok=True, no offenders."""
    assets = [
        {"asset_id": "oci:x:1", "category": "docker_container", "project": "openwebui"},
        {"asset_id": "oci:x:2", "category": "storage_mount", "project": "System"},
    ]
    rep = audit_ownership(assets, valid_projects=["openwebui"])
    assert rep["ok"] is True
    assert rep["missing_project"] == []
    assert rep["unknown_project"] == []
    assert rep["by_project"] == {"openwebui": 1, "System": 1}


def test_audit_ownership_catches_missing():
    """An asset with no project field is flagged."""
    assets = [{"asset_id": "oci:bad:1", "category": "docker_container"}]
    rep = audit_ownership(assets, valid_projects=["openwebui"])
    assert rep["ok"] is False
    assert len(rep["missing_project"]) == 1


def test_audit_ownership_catches_unknown_project():
    """An asset tagged with a project not on the valid list is flagged."""
    assets = [{"asset_id": "oci:bad:1", "category": "docker_container", "project": "Phantom"}]
    rep = audit_ownership(assets, valid_projects=["openwebui"])
    assert rep["ok"] is False
    assert rep["unknown_project"][0]["project"] == "Phantom"
