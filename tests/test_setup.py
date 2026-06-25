"""First-run setup — IP classification + settings persistence."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.routers import setup as S


def test_classify_addresses():
    assert S._classify("80.225.195.84", "enp0s6") == "public"
    assert S._classify("10.0.0.114", "enp0s6") == "private"      # VPC
    assert S._classify("192.168.1.10", "eth0") == "private"
    assert S._classify("100.107.140.36", "tailscale0") == "tailscale"
    assert S._classify("100.80.0.5", "eth0") == "cgnat"          # CGNAT range, non-ts iface
    assert S._classify("172.17.0.1", "docker0") == "docker"
    assert S._classify("10.8.0.1", "wg0") == "vpn"
    assert S._classify("127.0.0.1", "lo") == "loopback"


# tiny fake of db.db.settings
class _Settings:
    def __init__(self):
        self.doc = None

    def find_one(self, q):
        return self.doc

    def update_one(self, q, u, upsert=False):
        self.doc = {**(self.doc or {"_id": "app"}), **u["$set"]}


class _DB:
    def __init__(self):
        self.settings = _Settings()


class _FakeDB:
    def __init__(self):
        self.db = _DB()


def test_settings_roundtrip():
    db = _FakeDB()
    assert S._settings(db) == {}
    S._save_settings(db, {"setup_complete": True, "role": "primary"})
    s = S._settings(db)
    assert s["setup_complete"] is True
    assert s["role"] == "primary"
