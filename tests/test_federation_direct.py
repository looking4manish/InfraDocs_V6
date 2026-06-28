"""Direct (mesh) federation: the bidirectional enroll reachability gate (now also
carrying a priority that the primary checks for uniqueness) + the secondary wizard wiring.

The cluster election + promote live in test_priority_cluster.py / test_cluster_endpoints.py.
"""

import os
import sys
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

DIRECT_TEST_DB = "infradocs_direct_test"


def _auth():
    cfg = load_config(str(ROOT / "config.yml"))
    return (cfg.auth.username, os.environ.get(cfg.auth.password_env) or cfg.auth.dev_password)


AUTH = _auth()


@pytest.fixture
def db():
    cfg = load_config(str(ROOT / "config.yml"))
    if not os.environ.get(cfg.mongodb.uri_env):
        pytest.skip("MongoDB URI not configured")
    d = DBManager(uri=cfg.mongodb.uri, database=DIRECT_TEST_DB)
    yield d
    d.client.drop_database(DIRECT_TEST_DB)
    d.close()


@pytest.fixture
def client(db):
    cfg = load_config(str(ROOT / "config.yml"))
    app.dependency_overrides[api_deps.get_db] = lambda: db
    app.dependency_overrides[api_deps.get_config] = lambda: cfg
    yield TestClient(app)
    app.dependency_overrides.clear()


def _enroll_body(priority=5, sid="n150", url="http://100.72.146.5:8090", token="tok"):
    return {"server_id": sid, "secondary_url": url, "join_token": token, "priority": priority}


def test_enroll_both_directions_pass_records_priority(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "n150"})
    r = client.post("/api/federation/enroll", json=_enroll_body(priority=5))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["directions"] == {"secondary_to_primary": True, "primary_to_secondary": True}
    # roster row carries the priority + address
    rec = db.db.cluster_nodes.find_one({"node_id": "n150"})
    assert rec["priority"] == 5 and rec["address"] == "http://100.72.146.5:8090"


def test_enroll_primary_cannot_reach_back_refuses(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: (_ for _ in ()).throw(OSError("refused")))
    r = client.post("/api/federation/enroll", json=_enroll_body())
    body = r.json()
    assert body["ok"] is False
    assert body["directions"] == {"secondary_to_primary": True, "primary_to_secondary": False}
    assert db.db.cluster_nodes.find_one({"node_id": "n150"}) is None  # not enrolled


def test_enroll_bad_token_401(client, db, monkeypatch):
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "n150"})
    r = client.post("/api/federation/enroll", json=_enroll_body(token="nope"))
    assert r.status_code == 401


def test_enroll_identity_mismatch_refuses(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "imposter"})
    r = client.post("/api/federation/enroll", json=_enroll_body())
    assert r.json()["ok"] is False and "identifies as" in r.json()["reason"]


def test_enroll_with_primary_unreachable_primary(monkeypatch):
    monkeypatch.setattr(F, "_post_json", lambda *a, **k: (_ for _ in ()).throw(OSError("no route")))
    out = F.enroll_with_primary("https://primary", "http://me", "tok", "n150", 5)
    assert out["ok"] is False and out["directions"]["secondary_to_primary"] is False


def test_setup_secondary_refused_when_enroll_fails(client, monkeypatch):
    monkeypatch.setattr(F, "enroll_with_primary", lambda *a, **k: {
        "ok": False, "directions": {"secondary_to_primary": True, "primary_to_secondary": False},
        "reason": "primary could not reach the secondary"})
    r = client.post("/api/setup/complete", auth=AUTH, json={
        "role": "secondary", "primary_url": "https://p", "join_token": "tok",
        "advertise_url": "http://me", "priority": 5})
    assert r.status_code == 400
    assert r.json()["detail"]["directions"]["primary_to_secondary"] is False


def test_setup_secondary_succeeds_and_records_self(client, db, monkeypatch):
    monkeypatch.setattr(F, "enroll_with_primary", lambda *a, **k: {
        "ok": True, "directions": {"secondary_to_primary": True, "primary_to_secondary": True}})
    r = client.post("/api/setup/complete", auth=AUTH, json={
        "role": "secondary", "primary_url": "https://p", "join_token": "tok",
        "advertise_url": "http://me", "priority": 7})
    assert r.status_code == 200
    self_doc = db.db.cluster.find_one({"_id": "self"})
    assert self_doc["priority"] == 7 and self_doc["is_primary"] is False


def test_setup_secondary_missing_priority_400(client):
    r = client.post("/api/setup/complete", auth=AUTH, json={
        "role": "secondary", "primary_url": "https://p", "join_token": "tok", "advertise_url": "http://me"})
    assert r.status_code == 400
