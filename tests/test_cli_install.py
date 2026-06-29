"""Installer logic (app/cli_install.py) — prompt validation, priority-uniqueness
rejection (driving /api/cluster/health), reachability-fail refusal (driving
/api/setup/complete), config rendering, and the non-interactive deploy invocation.
All HTTP/subprocess is injected, so these run without a network or Docker."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.cli_install as I


# ----------------------- priority validation + uniqueness -------------------


def test_validate_priority_range():
    assert I.validate_priority(1)[0] is True
    assert I.validate_priority(99)[0] is True
    assert I.validate_priority(0)[0] is False
    assert I.validate_priority(100)[0] is False
    assert I.validate_priority("abc")[0] is False


def _health(priority=1, peers=()):
    return lambda url, timeout=8: {"node_id": "oci", "priority": priority,
                                   "peers": [{"node_id": n, "priority": p} for n, p in peers]}


def test_check_priority_rejects_duplicate_from_primary():
    getter = _health(priority=1, peers=[("n150", 3)])
    # 1 is the primary's, 3 is a peer's -> both rejected with a clear reason
    ok, reason = I.check_priority_free("http://primary", 1, getter=getter)
    assert ok is False and "already in use" in reason and "oci" in reason
    ok3, r3 = I.check_priority_free("http://primary", 3, getter=getter)
    assert ok3 is False and "n150" in r3
    # a free one is accepted
    assert I.check_priority_free("http://primary", 5, getter=getter)[0] is True


def test_check_priority_out_of_range_before_querying():
    called = {"n": 0}

    def getter(url, timeout=8):
        called["n"] += 1
        return {"node_id": "oci", "priority": 1, "peers": []}

    ok, reason = I.check_priority_free("http://primary", 0, getter=getter)
    assert ok is False and "out of range" in reason


def test_check_priority_primary_unreachable():
    def boom(url, timeout=8):
        raise OSError("no route")

    ok, reason = I.check_priority_free("http://primary", 5, getter=boom)
    assert ok is False and "could not reach the primary" in reason


def test_primary_reachable():
    assert I.primary_reachable("http://p", getter=lambda u, timeout=8: {"status": "ok"}) is True
    assert I.primary_reachable("http://p", getter=lambda u, timeout=8: (_ for _ in ()).throw(OSError())) is False


# ----------------------- config rendering -----------------------------------


def test_render_env_has_required_keys_and_no_mesh_assumption():
    env = I.render_env({"server_id": "node2", "admin_password": "S3cret", "web_port": 8081, "api_port": 8090})
    assert "SERVER_ID=node2" in env
    assert "ADMIN_PASSWORD=S3cret" in env
    assert "API_PORT=8090" in env
    # mesh-agnostic: no tailscale/cloudflare sidecar profiles or keys set
    assert "COMPOSE_PROFILES=\n" in env
    assert "TS_AUTHKEY=\n" in env
    assert "tailscale" not in env.lower()


def test_render_env_defaults():
    env = I.render_env({"server_id": "n"})
    assert "ADMIN_PASSWORD=Changeme001" in env
    assert "MONGO_PORT=27018" in env


def test_build_complete_body_primary_forces_priority_1():
    b = I.build_complete_body({"role": "primary", "advertise_url": "http://me"})
    assert b["priority"] == 1 and b["role"] == "primary"


def test_build_complete_body_secondary_carries_enroll_fields():
    b = I.build_complete_body({"role": "secondary", "advertise_url": "http://me",
                               "priority": "7", "primary_url": "http://p", "join_token": "tok"})
    assert b["priority"] == 7 and b["primary_url"] == "http://p" and b["join_token"] == "tok"


def test_build_complete_body_standalone_needs_no_address_or_peers():
    # A single-node install: priority auto-1, no advertise_url, no peer/token fields.
    b = I.build_complete_body({"role": "standalone", "server_name": "solo"})
    assert b["role"] == "standalone" and b["priority"] == 1
    assert b.get("advertise_url") is None
    assert "primary_url" not in b and "join_token" not in b


def test_cli_complete_standalone_accepts_no_advertise_url(monkeypatch):
    # --advertise-url is no longer required, so a standalone `complete` parses + runs.
    captured = {}

    def fake_complete(api_base, body, auth, poster=None):
        captured["body"] = body
        return True, None, None

    monkeypatch.setattr(I, "complete_setup", fake_complete)
    rc = I._cli(["complete", "--api", "http://local", "--role", "standalone",
                 "--server-name", "solo"])
    assert rc == 0
    assert captured["body"]["role"] == "standalone"
    assert captured["body"]["priority"] == 1
    assert captured["body"].get("advertise_url") is None
    assert "primary_url" not in captured["body"]


# ----------------------- enroll / setup completion --------------------------


def test_complete_setup_success():
    poster = lambda url, body, auth=None, timeout=20: (200, {"ok": True})
    ok, reason, directions = I.complete_setup("http://local", {"role": "secondary"}, ("admin", "pw"), poster=poster)
    assert ok is True and directions["primary_to_secondary"] is True


def test_complete_setup_reachability_failure_surfaces_directions():
    detail = {"message": "enrollment refused",
              "directions": {"secondary_to_primary": True, "primary_to_secondary": False},
              "reason": "primary could not reach the secondary at http://me"}
    poster = lambda url, body, auth=None, timeout=20: (400, {"detail": detail})
    ok, reason, directions = I.complete_setup("http://local", {"role": "secondary"}, ("admin", "pw"), poster=poster)
    assert ok is False
    assert directions["primary_to_secondary"] is False
    assert "could not reach" in reason


def test_complete_setup_priority_conflict_surfaces_reason():
    # a 409 from the primary becomes a 400 with a string detail at /complete
    poster = lambda url, body, auth=None, timeout=20: (400, {"detail": {"reason": "priority 3 already in use (by 'n150')"}})
    ok, reason, _ = I.complete_setup("http://local", {"role": "secondary"}, ("a", "b"), poster=poster)
    assert ok is False and "already in use" in reason


# ----------------------- non-interactive deploy -----------------------------


def test_deploy_invokes_deploy_sh_non_interactively():
    calls = {}

    def runner(cmd, env=None, check=False):
        calls["cmd"] = cmd
        calls["env"] = env
        return 0

    I.deploy("/repo", runner=runner, env={"PATH": "/usr/bin"})
    assert calls["cmd"] == ["bash", "/repo/deploy/docker/deploy.sh"]
    assert calls["env"]["INFRADOCS_NONINTERACTIVE"] == "1"
