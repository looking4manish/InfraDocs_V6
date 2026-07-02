"""Portless-address normalization + enroll error clarity (the tlsv1-alert bug).

Pure/unit — no network. Covers: normalize_url, public-IP detection ordering, the named
probe-failure reason (never a raw SSL alert), and the bidirectional gate naming a failed
direction. Normalization is asserted BOTH before the probe (what enroll sends) and before
storage (what enroll_secondary persists)."""

import json
import app.cli_install as I
import app.federation as F


# ---- normalize_url ---------------------------------------------------------

def test_normalize_url_adds_default_port():
    assert I.normalize_url("http://100.107.140.36") == "http://100.107.140.36:8081"
    assert I.normalize_url("100.107.140.36") == "http://100.107.140.36:8081"
    assert I.normalize_url("https://host") == "https://host:8081"

def test_normalize_url_keeps_explicit_port_and_path():
    assert I.normalize_url("http://h:9000") == "http://h:9000"
    assert I.normalize_url("http://h/path") == "http://h:8081/path"
    assert I.normalize_url("") == ""


# ---- detection: public IPv4 labelled + ranked last -------------------------

def test_detect_addresses_public_ip_labelled_and_last():
    from types import SimpleNamespace
    ipjson = json.dumps([
        {"ifname": "eth0", "addr_info": [{"family": "inet", "local": "1.2.3.4"}]},
        {"ifname": "ts0",  "addr_info": [{"family": "inet", "local": "100.107.140.36"}]},
        {"ifname": "lan0", "addr_info": [{"family": "inet", "local": "10.0.0.9"}]},
    ])
    def runner(cmd, **k):
        s = " ".join(cmd)
        if s.startswith("tailscale ip"): return SimpleNamespace(returncode=0, stdout="100.107.140.36\n")
        if s.startswith("ip -j"):        return SimpleNamespace(returncode=0, stdout=ipjson)
        return SimpleNamespace(returncode=1, stdout="")
    cands = I.detect_addresses(8081, runner=runner)
    kinds = [c["kind"] for c in cands]
    assert kinds[0] == "tailscale"                 # never public as default
    assert kinds[-1] == "public"                   # public ranked last
    pub = next(c for c in cands if c["kind"] == "public")
    assert pub["url"] == "http://1.2.3.4:8081" and "firewall" in pub["label"]


# ---- probe failure reason: named, never a raw SSL alert --------------------

def test_probe_failure_reason_translates_tls_alert():
    r = F.probe_failure_reason("http://100.107.140.36",
                               Exception("[SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error (_ssl.c:1000)"))
    assert "tlsv1 alert internal error" not in r
    assert "missing-port" in r and ":8081" in r

def test_probe_failure_reason_unreachable_is_firewall_likely():
    r = F.probe_failure_reason("http://10.0.0.5:8081", Exception("[Errno 111] Connection refused"))
    assert "unreachable" in r and "firewall" in r


# ---- enroll normalizes the probe input; names a failed direction -----------

def test_enroll_with_primary_normalizes_probe_input(monkeypatch):
    sent = {}
    def fake_post(url, body, headers=None, timeout=25):
        sent["url"] = url; sent["body"] = body
        return {"ok": True, "directions": {"secondary_to_primary": True, "primary_to_secondary": True}}
    monkeypatch.setattr(F, "_post_json", fake_post)
    F.enroll_with_primary("http://100.107.140.36", "http://10.0.0.5", "tok", "n2", 2)
    assert sent["url"].startswith("http://100.107.140.36:8081")     # primary normalized
    assert sent["body"]["secondary_url"] == "http://10.0.0.5:8081"  # secondary normalized BEFORE probe

def test_enroll_with_primary_names_direction_on_unreachable(monkeypatch):
    def boom(url, body, headers=None, timeout=25): raise Exception("[Errno 111] Connection refused")
    monkeypatch.setattr(F, "_post_json", boom)
    res = F.enroll_with_primary("http://p:8081", "http://s:8081", "t", "n2", 2)
    assert res["ok"] is False
    assert res["directions"]["secondary_to_primary"] is False
    assert "secondary→primary" in res["reason"]
    assert "tlsv1" not in res["reason"].lower()


# ---- enroll_secondary normalizes BEFORE storage ----------------------------

class _Coll:
    def __init__(self): self.updates = []
    def update_one(self, flt, upd, upsert=False): self.updates.append((flt, upd))
class _DB:
    def __init__(self): self.cluster = _Coll()
class _DBW:
    def __init__(self): self.db = _DB()

def test_enroll_secondary_normalizes_before_storage(monkeypatch):
    import app.api.routers.setup as S
    captured = {}
    def fake_enroll(primary_url, advertise_url, join_token, server_id, priority, timeout=10):
        captured["primary"] = primary_url; captured["advertise"] = advertise_url
        return {"ok": True}
    monkeypatch.setattr(F, "enroll_with_primary", fake_enroll)
    db = _DBW()
    res = S.enroll_secondary(db, "n2", "http://100.107.140.36", "tok", "http://10.0.0.5", 2)
    assert res["ok"]
    assert captured["advertise"] == "http://10.0.0.5:8081"          # before probe
    assert captured["primary"] == "http://100.107.140.36:8081"
    stored = db.db.cluster.updates[-1][1]["$set"]["address"]
    assert stored == "http://10.0.0.5:8081"                         # before storage
