"""Caddy + Cloudflare-tunnel exposure detectors — parsing + asset shape."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.scanners.caddy import CaddyScanner, parse_caddyfile
from app.scanners import cloudflared as cf_mod
from app.scanners.cloudflared import CloudflaredScanner


class _FakePD:
    def get_project_from_domain(self, d):
        return "System"


# ---- Caddy ----

def test_caddy_parse_multiple_sites_and_addresses():
    text = """
example.com {
    reverse_proxy localhost:3000
}
api.example.com, www.api.example.com {
    reverse_proxy 10.0.0.5:8080
}
"""
    sites = parse_caddyfile(text)
    assert len(sites) == 2
    assert sites[0]["addresses"] == ["example.com"]
    assert "localhost:3000" in sites[0]["upstreams"]
    assert set(sites[1]["addresses"]) == {"api.example.com", "www.api.example.com"}
    assert "10.0.0.5:8080" in sites[1]["upstreams"]


def test_caddy_parse_nested_handle_blocks():
    text = """
chat.example.com {
    handle /api/* {
        reverse_proxy localhost:8004
    }
    handle {
        reverse_proxy localhost:3000
    }
}
"""
    sites = parse_caddyfile(text)
    assert len(sites) == 1
    assert sites[0]["addresses"] == ["chat.example.com"]
    assert "localhost:8004" in sites[0]["upstreams"]
    assert "localhost:3000" in sites[0]["upstreams"]


def test_caddy_asset_skips_localhost_sets_port():
    s = CaddyScanner("oci", _FakePD())
    a = s._make_asset("chat.example.com", ["localhost:3000"], "/etc/caddy/Caddyfile")
    assert a["category"] == "caddy_site"
    assert a["metadata"]["upstream_port"] == 3000
    assert a["metadata"]["exposure_via"] == "caddy"
    assert a["health_indicators"]["internet_exposed"] is True


# ---- Cloudflare tunnel ----

def test_cloudflared_parses_ingress_and_skips_catchall(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yml"
    cfg.write_text(
        "tunnel: abc-123\n"
        "ingress:\n"
        "  - hostname: chat.example.com\n"
        "    service: http://localhost:3000\n"
        "  - hostname: api.example.com\n"
        "    service: http://localhost:8080\n"
        "  - service: http_status:404\n"
    )
    monkeypatch.setattr(cf_mod, "read_host_configs", lambda globs: [(str(cfg), cfg.read_text())])
    monkeypatch.setattr(cf_mod, "_running", lambda: True)
    assets = CloudflaredScanner("oci", _FakePD()).scan()

    assert len(assets) == 2  # catch-all (no hostname) skipped
    chat = next(a for a in assets if a["name"] == "chat.example.com")
    assert chat["category"] == "cloudflare_tunnel"
    assert chat["metadata"]["upstream_port"] == 3000
    assert chat["metadata"]["tunnel"] == "abc-123"
    assert chat["metadata"]["exposure_via"] == "cloudflare_tunnel"
    assert chat["health_indicators"]["internet_exposed"] is True
    assert chat["status"] == "active"


def test_cloudflared_no_config_is_clean(monkeypatch):
    monkeypatch.setattr(cf_mod, "read_host_configs", lambda globs: [])
    monkeypatch.setattr(cf_mod, "_running", lambda: False)
    assert CloudflaredScanner("oci", _FakePD()).scan() == []


def test_cloudflared_token_tunnel_when_running_no_config(monkeypatch):
    monkeypatch.setattr(cf_mod, "read_host_configs", lambda globs: [])
    monkeypatch.setattr(cf_mod, "_running", lambda: True)
    assets = CloudflaredScanner("oci", _FakePD()).scan()
    assert len(assets) == 1
    assert assets[0]["health_indicators"]["internet_exposed"] is True
    assert "remote-managed" in assets[0]["name"]
