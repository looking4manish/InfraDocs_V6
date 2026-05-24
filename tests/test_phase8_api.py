"""Phase 8 — action API tests (TestClient + mocked dispatcher)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.actions import ActionResult
from app.api import dependencies as api_deps
from app.api.main import app
from app.core.config_loader import load_config
from app.core.db_manager import DBManager


PHASE8_TEST_DB = "infradocs_phase8_test"


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
    test_db = DBManager(uri=cfg.mongodb.uri, database=PHASE8_TEST_DB)
    test_db.create_indexes()

    # Seed assets the actions endpoint will resolve.
    sample_assets = [
        {
            "server_id": "oci",
            "asset_id": "oci:container:abc123",
            "category": "docker_container",
            "name": "openwebui",
            "status": "running",
            "project": "openwebui",
            "metadata": {"container_id": "abc123"},
            "health_indicators": {"running": True},
        },
        {
            "server_id": "oci",
            "asset_id": "oci:service:my.service",
            "category": "systemd_service",
            "name": "my.service",
            "status": "active",
            "project": "openwebui",
            "metadata": {"unit_type": "service"},
            "health_indicators": {"active": True},
        },
        {
            "server_id": "oci",
            "asset_id": "oci:service:infradocs-v6-api.service",
            "category": "systemd_service",
            "name": "infradocs-v6-api.service",
            "status": "active",
            "project": "InfraDocs_V6",
            "metadata": {"unit_type": "service"},
        },
        {
            "server_id": "oci",
            "asset_id": "oci:mount:/",
            "category": "storage_mount",
            "name": "/",
            "status": "mounted",
            "project": "System",
            "metadata": {},
        },
        {
            "server_id": "oci",
            "asset_id": "oci:image:abc123def",
            "category": "docker_image",
            "name": "openwebui:latest",
            "status": "in_use",
            "project": "System",
            "metadata": {"tags": ["openwebui:latest"]},
        },
    ]
    for a in sample_assets:
        test_db.upsert_asset(a)

    # Seed an application with one container + one systemd_unit
    test_db.replace_applications([
        {
            "name": "openwebui",
            "application_id": "oci:app:openwebui",
            "type": "project",
            "containers": ["openwebui"],
            "systemd_units": ["my.service"],
            "nginx_sites": [],
            "urls": [],
            "components_count": 2,
        },
    ])

    app.dependency_overrides[api_deps.get_db] = lambda: test_db
    app.dependency_overrides[api_deps.get_config] = lambda: cfg

    yield TestClient(app)

    app.dependency_overrides.clear()
    test_db.client.drop_database(PHASE8_TEST_DB)
    test_db.close()


# --------------------------- asset action endpoint --------------------------


def test_action_404_for_unknown_asset(client):
    r = client.post(
        "/api/assets/oci:container:nope/action",
        json={"action": "start"},
        auth=AUTH,
    )
    assert r.status_code == 404


def test_action_403_for_disallowed_action(client):
    r = client.post(
        "/api/assets/oci:container:abc123/action",
        json={"action": "delete"},
        auth=AUTH,
    )
    assert r.status_code == 403


def test_action_403_for_category_with_no_actions(client):
    """docker_image has no entries in ALLOWED_ACTIONS — any action → 403."""
    r = client.post(
        "/api/assets/oci:image:abc123def/action",
        json={"action": "restart"},
        auth=AUTH,
    )
    assert r.status_code == 403


def test_action_409_for_self_protect(client):
    r = client.post(
        "/api/assets/oci:service:infradocs-v6-api.service/action",
        json={"action": "restart"},
        auth=AUTH,
    )
    assert r.status_code == 409
    assert "protected" in r.json()["detail"]


def test_container_restart_dispatches_and_audits(client):
    with patch("app.api.routers.actions.dispatch") as d:
        d.return_value = ActionResult(
            status="success", stdout="restarted openwebui", duration_ms=42
        )
        r = client.post(
            "/api/assets/oci:container:abc123/action",
            json={"action": "restart"},
            auth=AUTH,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["duration_ms"] == 42

    # Audit log written
    r2 = client.get("/api/actions/?asset_id=oci:container:abc123", auth=AUTH)
    audit = r2.json()
    assert audit["count"] >= 1
    assert audit["actions"][0]["action"] == "restart"
    assert audit["actions"][0]["actor"] == "msinha"
    assert audit["actions"][0]["status"] == "success"


def test_disallowed_action_is_also_audited(client):
    """A 403 response still writes an audit row, with refused_reason set."""
    client.post(
        "/api/assets/oci:container:abc123/action",
        json={"action": "delete"},
        auth=AUTH,
    )
    rows = client.get(
        "/api/actions/?asset_id=oci:container:abc123&action=delete",
        auth=AUTH,
    ).json()["actions"]
    assert rows
    assert rows[0]["refused_reason"] == "not_allowed"


def test_self_action_is_audited_with_reason(client):
    client.post(
        "/api/assets/oci:service:infradocs-v6-api.service/action",
        json={"action": "restart"},
        auth=AUTH,
    )
    rows = client.get(
        "/api/actions/?asset_id=oci:service:infradocs-v6-api.service",
        auth=AUTH,
    ).json()["actions"]
    assert any(r.get("refused_reason") == "self_protect" for r in rows)


# --------------------------- application action endpoint -------------------


def test_application_action_404_for_unknown_app(client):
    r = client.post(
        "/api/applications/Nonexistent/action",
        json={"action": "restart"},
        auth=AUTH,
    )
    assert r.status_code == 404


def test_application_restart_fans_out_to_each_asset(client):
    with patch("app.api.routers.actions.dispatch") as d:
        d.return_value = ActionResult(status="success", stdout="ok", duration_ms=1)
        r = client.post(
            "/api/applications/openwebui/action",
            json={"action": "restart"},
            auth=AUTH,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["application"] == "openwebui"
    assert body["targets"] == 2  # 1 container + 1 systemd
    assert all(res["status"] == "success" for res in body["results"])
    # Both an asset_id for the container and one for the service
    seen_categories = {res["category"] for res in body["results"]}
    assert seen_categories == {"docker_container", "systemd_service"}


def test_app_action_mixed_success_and_skip(client):
    """If an action is valid for some categories but not others, the
    targets get individual statuses instead of one global failure."""
    with patch("app.api.routers.actions.dispatch") as d:
        # `up` is allowed for compose only, not container/systemd. The
        # dispatcher would normally raise ActionNotAllowed. Simulate.
        from app.actions import ActionNotAllowed
        d.side_effect = ActionNotAllowed("nope")
        r = client.post(
            "/api/applications/openwebui/action",
            json={"action": "up"},
            auth=AUTH,
        )
    body = r.json()
    assert r.status_code == 200
    assert all(res["status"] == "skipped" for res in body["results"])


# --------------------------- listing actions --------------------------------


def test_list_actions_filters(client):
    with patch("app.api.routers.actions.dispatch") as d:
        d.return_value = ActionResult(status="success", duration_ms=1)
        client.post("/api/assets/oci:container:abc123/action",
                    json={"action": "start"}, auth=AUTH)
        client.post("/api/assets/oci:container:abc123/action",
                    json={"action": "stop"}, auth=AUTH)

    rows = client.get("/api/actions/?action=stop", auth=AUTH).json()["actions"]
    assert all(r["action"] == "stop" for r in rows)


def test_list_allowed(client):
    r = client.get("/api/actions/allowed", auth=AUTH)
    body = r.json()
    assert "allowed" in body
    assert set(body["allowed"]["docker_container"]) == {"start", "stop", "restart", "logs"}


def test_actions_auth_required(client):
    r = client.post("/api/assets/oci:container:abc123/action", json={"action": "start"})
    assert r.status_code == 401
