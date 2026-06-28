"""Direct (mesh) federation: bidirectional enroll reachability + Mongo-lease
leader election + guarded manual promote.

Three layers:
  - reachability: the enroll handshake only succeeds when BOTH directions prove
    reachable (mocked back-connection).
  - lease: the atomic acquire/renew/expire arbitration (real test DB).
  - promote: refuse when a live leader exists; allow when none; force only behind
    the explicit flag and never against a confirmed-live leader.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.cluster_lease as CL
import app.federation as F
from app.api import dependencies as api_deps
from app.api.main import app
from app.core.config_loader import load_config
from app.core.db_manager import DBManager

DIRECT_TEST_DB = "infradocs_direct_test"
NOW = datetime(2026, 6, 28, 9, 0, 0, tzinfo=timezone.utc)


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


NODE_ID = load_config(str(ROOT / "config.yml")).server.id  # "oci"


# ===========================================================================
# 1. Reachability — the bidirectional enroll handshake
# ===========================================================================


def test_enroll_both_directions_pass_enrolls(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    # primary's back-connection to the secondary succeeds and identifies as n150
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "n150"})
    r = client.post("/api/federation/enroll",
                    json={"server_id": "n150", "secondary_url": "http://100.72.146.5:8090", "join_token": "tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["directions"] == {"secondary_to_primary": True, "primary_to_secondary": True}
    # enrollment persisted WITH the address so the primary can reach back later
    srv = db.db.federation_servers.find_one({"server_id": "n150"})
    assert srv and srv["url"] == "http://100.72.146.5:8090"


def test_enroll_primary_cannot_reach_back_refuses(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})

    def _unreachable(url, timeout=8):
        raise OSError("connection refused")

    monkeypatch.setattr(F, "ping_node", _unreachable)
    r = client.post("/api/federation/enroll",
                    json={"server_id": "n150", "secondary_url": "http://bad:8090", "join_token": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["directions"] == {"secondary_to_primary": True, "primary_to_secondary": False}
    assert "could not reach" in body["reason"]
    # NOT enrolled on a failed back-connection
    assert db.db.federation_servers.find_one({"server_id": "n150"}) is None


def test_enroll_bad_token_401(client, db, monkeypatch):
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "n150"})
    r = client.post("/api/federation/enroll",
                    json={"server_id": "n150", "secondary_url": "http://x", "join_token": "nope"})
    assert r.status_code == 401


def test_enroll_identity_mismatch_refuses(client, db, monkeypatch):
    db.db.join_tokens.insert_one({"token": "tok", "server_id": "n150"})
    # the box we reached back claims to be someone else
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: {"ok": True, "server_id": "imposter"})
    r = client.post("/api/federation/enroll",
                    json={"server_id": "n150", "secondary_url": "http://x", "join_token": "tok"})
    body = r.json()
    assert body["ok"] is False and "identifies as" in body["reason"]


def test_enroll_with_primary_unreachable_primary(monkeypatch):
    # secondary-side helper: if the primary itself is unreachable, secondary->primary fails
    def _boom(url, body, headers=None, timeout=25):
        raise OSError("no route to host")

    monkeypatch.setattr(F, "_post_json", _boom)
    out = F.enroll_with_primary("https://primary", "http://me", "tok", "n150")
    assert out["ok"] is False
    assert out["directions"]["secondary_to_primary"] is False


def test_setup_secondary_refused_when_enroll_fails(client, monkeypatch):
    monkeypatch.setattr(F, "enroll_with_primary", lambda *a, **k: {
        "ok": False, "directions": {"secondary_to_primary": True, "primary_to_secondary": False},
        "reason": "primary could not reach the secondary",
    })
    r = client.post("/api/setup/complete", auth=AUTH, json={
        "role": "secondary", "primary_url": "https://p", "join_token": "tok", "advertise_url": "http://me"})
    assert r.status_code == 400
    assert r.json()["detail"]["directions"]["primary_to_secondary"] is False


def test_setup_secondary_succeeds_when_enroll_passes(client, db, monkeypatch):
    monkeypatch.setattr(F, "enroll_with_primary", lambda *a, **k: {
        "ok": True, "directions": {"secondary_to_primary": True, "primary_to_secondary": True}})
    r = client.post("/api/setup/complete", auth=AUTH, json={
        "role": "secondary", "primary_url": "https://p", "join_token": "tok", "advertise_url": "http://me"})
    assert r.status_code == 200
    assert db.db.settings.find_one({"_id": "app"})["role"] == "secondary"


def test_setup_secondary_missing_advertise_url_400(client):
    r = client.post("/api/setup/complete", auth=AUTH, json={
        "role": "secondary", "primary_url": "https://p", "join_token": "tok"})
    assert r.status_code == 400


# ===========================================================================
# 2. Lease — atomic acquire / renew / expire
# ===========================================================================


def test_lease_first_acquire_wins_and_is_leader(db):
    assert CL.try_acquire_or_renew(db.db, "A", 15, now=NOW) is True
    assert CL.is_leader(db.db, "A", now=NOW) is True
    st = CL.lease_state(db.db, now=NOW)
    assert st["holder"] == "A" and st["valid"] is True


def test_lease_cannot_be_stolen_while_valid(db):
    assert CL.try_acquire_or_renew(db.db, "A", 15, now=NOW) is True
    # B tries 1s later while A's lease is still valid -> loses
    later = NOW + timedelta(seconds=1)
    assert CL.try_acquire_or_renew(db.db, "B", 15, now=later) is False
    assert CL.lease_state(db.db, now=later)["holder"] == "A"
    assert CL.is_leader(db.db, "B", now=later) is False


def test_lease_exactly_one_winner_in_a_race(db):
    # All five contenders attempt acquisition at the SAME instant on an empty lease.
    # The atomic single-document upsert (+ unique _id) guarantees exactly one wins.
    wins = [CL.try_acquire_or_renew(db.db, f"node{i}", 15, now=NOW) for i in range(5)]
    assert wins.count(True) == 1
    holder = CL.lease_state(db.db, now=NOW)["holder"]
    assert holder == "node0"  # the first to run; the other four hit the live-lease guard


def test_lease_renewal_extends_expiry(db):
    CL.try_acquire_or_renew(db.db, "A", 15, now=NOW)
    first_exp = CL.lease_state(db.db, now=NOW)["expires_at"]
    # renew 5s later (still mine, still valid)
    renew_at = NOW + timedelta(seconds=5)
    assert CL.try_acquire_or_renew(db.db, "A", 15, now=renew_at) is True
    second_exp = CL.lease_state(db.db, now=renew_at)["expires_at"]
    assert second_exp > first_exp


def test_expired_lease_is_acquirable_by_another_and_old_leader_steps_down(db):
    CL.try_acquire_or_renew(db.db, "A", 15, now=NOW)
    # A goes dark; 20s later (past the 15s TTL) the lease is expired
    after = NOW + timedelta(seconds=20)
    assert CL.is_leader(db.db, "A", now=after) is False        # A's belief no longer holds
    assert CL.try_acquire_or_renew(db.db, "B", 15, now=after) is True
    assert CL.is_leader(db.db, "B", now=after) is True
    assert CL.is_leader(db.db, "A", now=after) is False        # A is not the leader anymore


def test_force_acquire_seizes_a_live_lease(db):
    CL.try_acquire_or_renew(db.db, "A", 15, now=NOW)
    st = CL.force_acquire(db.db, "B", 15, now=NOW)             # while A's lease is valid
    assert st["holder"] == "B" and st["forced"] is True
    assert CL.is_leader(db.db, "B", now=NOW) is True


def test_release_lets_a_peer_take_over_immediately(db):
    CL.try_acquire_or_renew(db.db, "A", 15, now=NOW)
    assert CL.release(db.db, "A", now=NOW) is True
    # released -> expired now -> B can take it at the same instant
    assert CL.try_acquire_or_renew(db.db, "B", 15, now=NOW) is True
    # a node that doesn't hold the lease can't release it
    assert CL.release(db.db, "A", now=NOW) is False


# ===========================================================================
# 3. Manual promote — the guard
# ===========================================================================


def test_promote_refused_when_live_leader_exists(client, db):
    db.db.cluster_lease.insert_one(
        {"_id": CL.LEASE_ID, "holder": "other", "expires_at": NOW + timedelta(hours=1)})
    r = client.post("/api/federation/promote", auth=AUTH, json={"force": False})
    assert r.status_code == 200
    body = r.json()
    assert body["promoted"] is False and body["leader"] == "other"


def test_promote_allowed_when_no_leader(client, db):
    # empty lease, no peers
    r = client.post("/api/federation/promote", auth=AUTH, json={"force": False})
    body = r.json()
    assert body["promoted"] is True and body["leader"] == NODE_ID
    assert CL.lease_state(db.db)["holder"] == NODE_ID


def test_promote_needs_force_when_a_node_is_unreachable(client, db, monkeypatch):
    db.db.federation_servers.insert_one({"server_id": "n150", "url": "http://100.72.146.5:8090"})

    def _unreachable(url, timeout=8):
        raise OSError("unreachable")

    monkeypatch.setattr(F, "ping_node", _unreachable)
    r = client.post("/api/federation/promote", auth=AUTH, json={"force": False})
    body = r.json()
    assert body["promoted"] is False
    assert body["needs_force"] is True
    assert body["unreachable"] == ["n150"]
    # did NOT acquire
    assert CL.lease_state(db.db)["holder"] is None


def test_promote_force_acquires_despite_unreachable(client, db, monkeypatch):
    db.db.federation_servers.insert_one({"server_id": "n150", "url": "http://100.72.146.5:8090"})
    monkeypatch.setattr(F, "ping_node", lambda url, timeout=8: (_ for _ in ()).throw(OSError("x")))
    r = client.post("/api/federation/promote", auth=AUTH, json={"force": True})
    body = r.json()
    assert body["promoted"] is True and body["forced"] is True
    assert CL.is_leader(db.db, NODE_ID) is True


def test_promote_force_still_refused_against_a_confirmed_live_leader(client, db, monkeypatch):
    # lease empty, but a reachable peer reports it IS a live leader -> force must not steal it
    db.db.federation_servers.insert_one({"server_id": "n150", "url": "http://100.72.146.5:8090"})
    monkeypatch.setattr(F, "ping_node",
                        lambda url, timeout=8: {"server_id": "n150", "leader": {"valid": True, "holder": "n150"}})
    r = client.post("/api/federation/promote", auth=AUTH, json={"force": True})
    body = r.json()
    assert body["promoted"] is False
    assert "n150" in body["reason"]
