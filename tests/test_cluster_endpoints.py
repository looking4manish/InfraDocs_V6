"""Cluster endpoints (DB-backed): first-node-primary + priority uniqueness on enroll,
the guarded manual promote (roster-based), override, and cluster state."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.federation as F
from app.api import dependencies as api_deps
from app.api.main import app
from app.core.config_loader import load_config
from app.core.db_manager import DBManager

CLUSTER_TEST_DB = "infradocs_cluster_test"


def _auth():
    cfg = load_config(str(ROOT / "config.yml"))
    return (cfg.auth.username, os.environ.get(cfg.auth.password_env) or cfg.auth.dev_password)


AUTH = _auth()
NODE_ID = load_config(str(ROOT / "config.yml")).server.id  # "oci"


@pytest.fixture
def db():
    cfg = load_config(str(ROOT / "config.yml"))
    if not os.environ.get(cfg.mongodb.uri_env):
        pytest.skip("MongoDB URI not configured")
    d = DBManager(uri=cfg.mongodb.uri, database=CLUSTER_TEST_DB)
    yield d
    d.client.drop_database(CLUSTER_TEST_DB)
    d.close()


@pytest.fixture
def client(db):
    cfg = load_config(str(ROOT / "config.yml"))
    app.dependency_overrides[api_deps.get_db] = lambda: db
    app.dependency_overrides[api_deps.get_config] = lambda: cfg
    yield TestClient(app)
    app.dependency_overrides.clear()


def _ago(seconds):
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


# ----------------------- first node + priority uniqueness -------------------


def test_first_node_setup_is_primary_priority_1(client, db):
    r = client.post("/api/setup/complete", auth=AUTH, json={"role": "primary", "advertise_url": "http://oci"})
    assert r.status_code == 200
    s = db.db.cluster.find_one({"_id": "self"})
    assert s["is_primary"] is True and s["priority"] == 1
    assert db.db.settings.find_one({"_id": "app"})["primary_node"] == NODE_ID


def test_enroll_rejects_duplicate_priority(client, db, monkeypatch):
    db.db.cluster.update_one({"_id": "self"}, {"$set": {"node_id": NODE_ID, "priority": 1}}, upsert=True)
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "n150"})
    # priority 1 is taken by the primary -> rejected with a clear message
    dup = client.post("/api/federation/enroll",
                      json={"server_id": "n150", "secondary_url": "http://n", "join_token": "tok", "priority": 1})
    assert dup.status_code == 409
    assert "already in use" in dup.json()["detail"]
    # a free priority is accepted
    ok = client.post("/api/federation/enroll",
                     json={"server_id": "n150", "secondary_url": "http://n", "join_token": "tok", "priority": 3})
    assert ok.status_code == 200 and ok.json()["ok"] is True


def test_enroll_priority_out_of_range_400(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"server_id": "n150"})
    for bad in (0, 100, -1):
        r = client.post("/api/federation/enroll",
                        json={"server_id": "n150", "secondary_url": "http://n", "join_token": "tok", "priority": bad})
        assert r.status_code == 400


# ----------------------- guarded manual promote -----------------------------


def test_promote_refused_vs_live_primary(client, db):
    db.db.cluster_nodes.insert_one(
        {"node_id": "n150", "priority": 2, "is_primary": True, "last_seen": _ago(2), "address": "http://n"})
    r = client.post("/api/cluster/promote", auth=AUTH, json={"force": False})
    body = r.json()
    assert body["promoted"] is False and body["leader"] == "n150"


def test_promote_allowed_when_no_live_primary(client, db):
    # a reachable peer that is NOT primary -> safe to promote self
    db.db.cluster_nodes.insert_one(
        {"node_id": "n150", "priority": 2, "is_primary": False, "last_seen": _ago(2), "address": "http://n"})
    r = client.post("/api/cluster/promote", auth=AUTH, json={"force": False})
    assert r.json()["promoted"] is True
    assert db.db.cluster.find_one({"_id": "self"})["is_primary"] is True


def test_promote_needs_force_when_node_unreachable(client, db):
    db.db.cluster_nodes.insert_one(
        {"node_id": "n150", "priority": 2, "is_primary": False, "last_seen": _ago(120), "address": "http://n"})
    r = client.post("/api/cluster/promote", auth=AUTH, json={"force": False})
    body = r.json()
    assert body["promoted"] is False and body["needs_force"] is True and body["unreachable"] == ["n150"]
    assert (db.db.cluster.find_one({"_id": "self"}) or {}).get("is_primary") is not True


def test_promote_force_acquires_despite_unreachable(client, db):
    db.db.cluster_nodes.insert_one(
        {"node_id": "n150", "priority": 2, "is_primary": False, "last_seen": _ago(120), "address": "http://n"})
    r = client.post("/api/cluster/promote", auth=AUTH, json={"force": True})
    body = r.json()
    assert body["promoted"] is True and body["forced"] is True
    assert db.db.cluster.find_one({"_id": "self"})["is_primary"] is True


# ----------------------- override + state -----------------------------------


def test_override_toggles_and_shows_in_state(client, db):
    db.db.cluster.update_one({"_id": "self"},
                             {"$set": {"node_id": NODE_ID, "priority": 1, "is_primary": True}}, upsert=True)
    assert client.post("/api/cluster/override", auth=AUTH, json={"value": True}).json()["override"] is True
    st = client.get("/api/cluster/state", auth=AUTH).json()
    assert st["override"] is True
    client.post("/api/cluster/override", auth=AUTH, json={"value": False})
    assert client.get("/api/cluster/state", auth=AUTH).json()["override"] is False


def test_state_reports_leader_and_majority(client, db):
    db.db.cluster.update_one({"_id": "self"},
                             {"$set": {"node_id": NODE_ID, "priority": 1, "is_primary": True}}, upsert=True)
    db.db.cluster_nodes.insert_one(
        {"node_id": "n150", "priority": 2, "is_primary": False, "last_seen": _ago(2), "address": "http://n"})
    st = client.get("/api/cluster/state", auth=AUTH).json()
    assert st["current_leader"] == NODE_ID          # this node serves as primary
    assert st["majority"] is True                    # 2 of 2 reachable
    assert {n["node_id"] for n in st["nodes"]} == {NODE_ID, "n150"}
