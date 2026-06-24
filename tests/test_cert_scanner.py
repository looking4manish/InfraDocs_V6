"""Cert scanner — openssl parsing + expiry/attribution (no host access)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.scanners.certs import CertScanner


class _FakePD:
    def get_project_from_domain(self, d):
        return "OCI_Dashboard" if "dashboard" in d else "System"


def test_parse_openssl_extracts_fields():
    text = (
        "notBefore=May 23 16:57:07 2026 GMT\n"
        "notAfter=Aug 21 16:57:06 2026 GMT\n"
        "issuer=C = US, O = Let's Encrypt, CN = E8\n"
        "subject=CN = carp.mdbdemo.in\n"
        "    X509v3 Subject Alternative Name:\n"
        "        DNS:carp.mdbdemo.in, DNS:www.carp.mdbdemo.in\n"
    )
    info = CertScanner._parse_openssl(text)
    assert info["not_after"] == "Aug 21 16:57:06 2026 GMT"
    assert "Let's Encrypt" in info["issuer"]
    assert info["sans"] == ["carp.mdbdemo.in", "www.carp.mdbdemo.in"]


def test_parse_not_after_future_past_and_garbage():
    days, expired = CertScanner._parse_not_after("Aug 21 16:57:06 2099 GMT")
    assert days > 0 and expired is False
    _, expired = CertScanner._parse_not_after("Aug 21 16:57:06 2000 GMT")
    assert expired is True
    assert CertScanner._parse_not_after(None) == (None, None)
    assert CertScanner._parse_not_after("garbage") == (None, None)


def test_make_asset_status_project_and_domains():
    s = CertScanner("oci", _FakePD())
    asset = s._make_asset(
        "dashboard.ocialwaysfree.site",
        "/etc/letsencrypt/live/dashboard.ocialwaysfree.site/fullchain.pem",
        {"not_after": "Aug 21 16:57:06 2099 GMT",
         "sans": ["dashboard.ocialwaysfree.site"], "issuer": "LE"},
    )
    assert asset["category"] == "tls_certificate"
    assert asset["status"] == "valid"
    assert asset["project"] == "OCI_Dashboard"
    assert asset["asset_id"] == "oci:cert:dashboard.ocialwaysfree.site"
    assert asset["metadata"]["domains"] == ["dashboard.ocialwaysfree.site"]


def test_make_asset_expiring_soon_flagged():
    s = CertScanner("oci", _FakePD())
    # ~10 days out → status 'expiring' + expiring_soon health flag
    from datetime import datetime, timedelta, timezone
    soon = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%b %d %H:%M:%S %Y GMT")
    asset = s._make_asset("x.example.com", "/x/fullchain.pem", {"not_after": soon})
    assert asset["status"] == "expiring"
    assert asset["health_indicators"]["expiring_soon"] is True
