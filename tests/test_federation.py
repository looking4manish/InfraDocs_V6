"""Federation — join-token validation + secondary push serialization."""

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.federation as F
from app.api.routers import federation as Fed


class _JT:
    def __init__(self, docs):
        self.docs = docs

    def find_one(self, q):
        return next((d for d in self.docs if d.get("token") == q.get("token")), None)


class _DB:
    def __init__(self, tokens):
        self.join_tokens = _JT(tokens)


class _FakeDB:
    def __init__(self, tokens):
        self.db = _DB(tokens)


def test_join_token_is_scoped_to_one_server():
    db = _FakeDB([{"token": "abc", "server_id": "n150"}])
    assert Fed._valid_token(db, "n150", "abc")
    assert not Fed._valid_token(db, "oci", "abc")     # token bound to n150 only
    assert not Fed._valid_token(db, "n150", "wrong")
    assert not Fed._valid_token(db, "n150", None)


def test_push_serializes_and_sets_token_header(monkeypatch):
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true, "assets": 1}'

    def fake_urlopen(req, timeout=0):
        captured["data"] = req.data
        captured["headers"] = req.headers
        captured["url"] = req.full_url
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    out = F.push_to_primary(
        "https://primary.example.com/",
        "tok123",
        "n150",
        [{"asset_id": "n150:x", "ts": datetime.now(timezone.utc)}],  # datetime must serialize
        [],
    )
    assert out["ok"] is True
    assert captured["url"].endswith("/api/federation/ingest")
    assert "tok123" in captured["headers"].values()
    body = json.loads(captured["data"])
    assert body["server_id"] == "n150"
    assert body["assets"][0]["asset_id"] == "n150:x"
