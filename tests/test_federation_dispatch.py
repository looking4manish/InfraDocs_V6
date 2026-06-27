"""Federation command dispatch (Model A — queue + outbound poll).

Two layers:
  - unit: poll_and_execute() runs the local dispatcher and reports back, with all
    requests outbound (mocked urlopen). Self-protection / not-allowed map to the
    right reported status.
  - api: the primary's enqueue/claim/result endpoints — token scoping, the
    infradocs-v6-* 409 refusal, and the actions_log audit trail.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.actions as A
import app.federation as F
from app.api import dependencies as api_deps
from app.api.main import app
from app.core.config_loader import load_config
from app.core.db_manager import DBManager
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------
# unit: secondary-side poll_and_execute
# --------------------------------------------------------------------------


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._p).encode()


def _pending_cmd():
    return {
        "command_id": "c1",
        "server_id": "n150",
        "asset": {
            "category": "docker_container",
            "asset_id": "n150:container:abc",
            "name": "web",
            "metadata": {"container_id": "abc"},
        },
        "action": "restart",
        "args": {},
    }


def _wire(monkeypatch):
    """Mock urlopen to serve one pending command and capture every POST."""
    posted = []

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        body = json.loads(req.data) if req.data else {}
        posted.append((url, body, dict(req.headers)))
        if url.endswith("/commands/pending"):
            return _Resp({"commands": [_pending_cmd()], "count": 1})
        if url.endswith("/result"):
            return _Resp({"ok": True})
        return _Resp({})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return posted


def test_poll_executes_dispatch_and_reports_success(monkeypatch):
    posted = _wire(monkeypatch)
    monkeypatch.setattr(
        A, "dispatch",
        lambda asset, action, args: A.ActionResult(status="success", stdout="restarted web"),
    )

    out = F.poll_and_execute("https://primary.example/", "tok", "n150")

    assert out["executed"] == 1
    assert out["results"][0]["status"] == "success"

    results = [p for p in posted if p[0].endswith("/result")]
    assert len(results) == 1
    url, body, headers = results[0]
    assert "/commands/c1/result" in url          # closed out the right command
    assert body["status"] == "success"
    assert body["stdout"] == "restarted web"
    assert "tok" in headers.values()             # outbound auth carried


def test_poll_reports_self_protect_as_refused(monkeypatch):
    posted = _wire(monkeypatch)

    def _refuse(asset, action, args):
        raise A.SelfActionRefused("refusing to act on protected asset: infradocs-v6-api")

    monkeypatch.setattr(A, "dispatch", _refuse)

    out = F.poll_and_execute("https://primary.example/", "tok", "n150")

    assert out["results"][0]["status"] == "refused"
    body = [p for p in posted if p[0].endswith("/result")][0][1]
    assert body["status"] == "refused"
    assert body["refused_reason"] == "self_protect"


def test_poll_reports_not_allowed_as_failed(monkeypatch):
    posted = _wire(monkeypatch)

    def _na(asset, action, args):
        raise A.ActionNotAllowed("action 'frobnicate' not allowed")

    monkeypatch.setattr(A, "dispatch", _na)

    out = F.poll_and_execute("https://primary.example/", "tok", "n150")

    assert out["results"][0]["status"] == "failed"
    body = [p for p in posted if p[0].endswith("/result")][0][1]
    assert body["refused_reason"] == "not_allowed"


# --------------------------------------------------------------------------
# api: primary-side enqueue / claim / result
# --------------------------------------------------------------------------

DISPATCH_TEST_DB = "infradocs_feddispatch_test"


def _resolve_auth():
    _cfg = load_config(str(ROOT / "config.yml"))
    return (
        _cfg.auth.username,
        os.environ.get(_cfg.auth.password_env) or _cfg.auth.dev_password,
    )


AUTH = _resolve_auth()
TOKEN = "n150-join-token"


@pytest.fixture
def client():
    cfg = load_config(str(ROOT / "config.yml"))
    if not os.environ.get(cfg.mongodb.uri_env):
        pytest.skip("MongoDB URI not configured")
    db = DBManager(uri=cfg.mongodb.uri, database=DISPATCH_TEST_DB)
    db.create_indexes()

    db.db.federation_servers.insert_one({
        "server_id": "n150",
        "last_seen": datetime.now(timezone.utc),
        "asset_count": 2,
        "app_count": 1,
    })
    db.db.join_tokens.insert_one({"token": TOKEN, "server_id": "n150"})
    for a in [
        {
            "server_id": "n150",
            "asset_id": "n150:container:web",
            "category": "docker_container",
            "name": "web",
            "project": "siteproj",
            "metadata": {"container_id": "web"},
        },
        {
            "server_id": "n150",
            "asset_id": "n150:service:infradocs-v6-api.service",
            "category": "systemd_service",
            "name": "infradocs-v6-api.service",
            "project": "InfraDocs_V6",
            "metadata": {"unit_type": "service"},
        },
    ]:
        db.upsert_asset(a)

    app.dependency_overrides[api_deps.get_db] = lambda: db
    app.dependency_overrides[api_deps.get_config] = lambda: cfg
    yield TestClient(app)
    app.dependency_overrides.clear()
    db.client.drop_database(DISPATCH_TEST_DB)
    db.close()


def _enqueue(client, asset_id="n150:container:web", action="restart"):
    return client.post(
        "/api/federation/commands",
        json={"server_id": "n150", "asset_id": asset_id, "action": action, "args": {}},
        auth=AUTH,
    )


def test_enqueue_creates_pending_command_and_audits(client):
    r = _enqueue(client)
    assert r.status_code == 200, r.text
    cid = r.json()["command_id"]
    assert r.json()["status"] == "pending"

    listing = client.get("/api/federation/commands?server_id=n150", auth=AUTH).json()
    assert any(c["command_id"] == cid and c["status"] == "pending" for c in listing["commands"])

    # The dispatch is audited the moment it's queued.
    audit = client.get("/api/actions/?asset_id=n150:container:web", auth=AUTH).json()
    assert any(a.get("command_id") == cid and a["status"] == "pending" for a in audit["actions"])


def test_enqueue_unknown_server_404(client):
    r = client.post(
        "/api/federation/commands",
        json={"server_id": "ghost", "asset_id": "n150:container:web", "action": "restart"},
        auth=AUTH,
    )
    assert r.status_code == 404


def test_enqueue_unknown_asset_404(client):
    r = _enqueue(client, asset_id="n150:container:nope")
    assert r.status_code == 404


def test_enqueue_self_protected_409(client):
    r = _enqueue(client, asset_id="n150:service:infradocs-v6-api.service")
    assert r.status_code == 409
    assert "protected" in r.json()["detail"]


def test_claim_pending_requires_valid_token(client):
    _enqueue(client)
    # no token
    assert client.post("/api/federation/commands/pending", json={"server_id": "n150"}).status_code == 401
    # wrong token
    bad = client.post(
        "/api/federation/commands/pending",
        json={"server_id": "n150"},
        headers={"X-Join-Token": "nope"},
    )
    assert bad.status_code == 401


def test_claim_then_result_round_trip_audits(client):
    cid = _enqueue(client).json()["command_id"]

    # secondary claims — command flips to dispatched and is returned once
    claim = client.post(
        "/api/federation/commands/pending",
        json={"server_id": "n150"},
        headers={"X-Join-Token": TOKEN},
    )
    assert claim.status_code == 200
    cmds = claim.json()["commands"]
    assert [c["command_id"] for c in cmds] == [cid]
    assert cmds[0]["status"] == "dispatched"

    # a re-poll must NOT hand the same command out again
    again = client.post(
        "/api/federation/commands/pending",
        json={"server_id": "n150"},
        headers={"X-Join-Token": TOKEN},
    )
    assert again.json()["count"] == 0

    # secondary reports success
    res = client.post(
        f"/api/federation/commands/{cid}/result",
        json={"server_id": "n150", "status": "success", "stdout": "restarted web", "duration_ms": 12},
        headers={"X-Join-Token": TOKEN},
    )
    assert res.status_code == 200

    listing = client.get("/api/federation/commands?server_id=n150", auth=AUTH).json()
    done = next(c for c in listing["commands"] if c["command_id"] == cid)
    assert done["status"] == "success"
    assert done["result"]["stdout"] == "restarted web"

    # final outcome is audited too
    audit = client.get("/api/actions/?asset_id=n150:container:web", auth=AUTH).json()
    assert any(a.get("command_id") == cid and a["status"] == "success" for a in audit["actions"])


def test_result_rejects_wrong_server_token(client):
    cid = _enqueue(client).json()["command_id"]
    # A token bound to a different server is valid for ITS server, but must not
    # be able to close n150's command.
    other_tok = client.post(
        "/api/federation/tokens", json={"server_id": "other"}, auth=AUTH
    ).json()["token"]
    r = client.post(
        f"/api/federation/commands/{cid}/result",
        json={"server_id": "other", "status": "success"},
        headers={"X-Join-Token": other_tok},
    )
    assert r.status_code == 403




def _insert_command(db, command_id, status, *, dispatched_at=None, created_at=None):

    """Insert a federation_commands row directly (bypassing enqueue) so we can

    control its age and status for reaper assertions."""

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    doc = {

        "command_id": command_id,

        "server_id": "n150",

        "asset": {

            "category": "docker_container",

            "asset_id": "n150:container:web",

            "name": "web",

            "project": "siteproj",

            "metadata": {"container_id": "web"},

        },

        "action": "restart",

        "args": {},

        "status": status,

        "created_at": created_at or now,

        "created_by": "tester",

    }

    if dispatched_at is not None:

        doc["dispatched_at"] = dispatched_at

    db.db.federation_commands.insert_one(doc)





def test_reaper_expires_stale_dispatched_commands(client):

    from datetime import datetime, timedelta, timezone

    db = app.dependency_overrides[api_deps.get_db]()

    now = datetime.now(timezone.utc)

    old = now - timedelta(seconds=901)        # just past the 900s window

    recent = now - timedelta(seconds=60)      # well inside the window



    _insert_command(db, "stale1", "dispatched", dispatched_at=old)

    _insert_command(db, "fresh1", "dispatched", dispatched_at=recent)

    _insert_command(db, "pend1", "pending")



    # GET /commands triggers reap-on-read.

    listing = client.get("/api/federation/commands?server_id=n150", auth=AUTH).json()

    by_id = {c["command_id"]: c for c in listing["commands"]}



    # Stale claimed command is expired; fresh and pending are untouched.

    assert by_id["stale1"]["status"] == "expired"

    assert by_id["fresh1"]["status"] == "dispatched"

    assert by_id["pend1"]["status"] == "pending"



    # The expiry is audited in actions_log, mirroring a real result close-out.

    audit = client.get("/api/actions/?asset_id=n150:container:web", auth=AUTH).json()

    assert any(

        a.get("command_id") == "stale1" and a["status"] == "expired"

        for a in audit["actions"]

    )



    # Reaper is idempotent — a second read doesn't re-expire or duplicate audits.

    client.get("/api/federation/commands?server_id=n150", auth=AUTH)

    audit2 = client.get("/api/actions/?asset_id=n150:container:web", auth=AUTH).json()

    expired_audits = [

        a for a in audit2["actions"]

        if a.get("command_id") == "stale1" and a["status"] == "expired"

    ]

    assert len(expired_audits) == 1

