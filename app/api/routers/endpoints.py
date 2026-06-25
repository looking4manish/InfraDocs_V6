"""Unified web/endpoint inventory across the fleet — every reachable UI/service,
how it's exposed, and where it lives. Generic: derives everything from scanned
assets (exposure blocks + listening ports), with no host-specific assumptions.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager

router = APIRouter()

# Well-known services by port — generic recognition (name, kind, is_web_ui).
KNOWN_PORTS = {
    80: ("HTTP", "web", True), 443: ("HTTPS", "web", True), 8080: ("HTTP-alt", "web", True),
    8000: ("web app", "web", True), 8081: ("web app", "web", True), 3000: ("web app", "web", True),
    5000: ("web app", "web", True), 8443: ("HTTPS-alt", "web", True), 5173: ("Vite dev server", "web", True),
    9090: ("Prometheus / Cockpit", "monitoring", True), 9100: ("node-exporter", "monitoring", True),
    3001: ("Grafana", "monitoring", True), 9091: ("Pushgateway", "monitoring", True),
    5601: ("Kibana", "monitoring", True), 9093: ("Alertmanager", "monitoring", True),
    27017: ("MongoDB", "database", False), 27018: ("MongoDB", "database", False),
    27028: ("MongoDB (mongot)", "database", False),
    5432: ("PostgreSQL", "database", False), 3306: ("MySQL", "database", False),
    6379: ("Redis", "database", False), 9200: ("Elasticsearch", "database", True),
    6333: ("Qdrant", "database", True), 6334: ("Qdrant gRPC", "database", False),
    8086: ("InfluxDB", "database", True), 2019: ("Caddy admin API", "infra", False),
}
# Wider scope = more reachable; we keep the widest address per port.
_SCOPE_RANK = {"public": 6, "all-interfaces": 5, "tailnet": 4, "private-lan": 3,
               "host": 2, "localhost": 1, "unknown": 0, "private": 0}


def _recognize(port: Optional[int]):
    return KNOWN_PORTS.get(port)


def _ip_of(addr: str) -> str:
    if not addr:
        return ""
    if addr.startswith("["):
        return addr[1:addr.index("]")] if "]" in addr else addr
    return addr.rsplit(":", 1)[0] if ":" in addr else addr


def _scope_from_addr(ip: str) -> str:
    if not ip:
        return "unknown"
    if ip in ("127.0.0.1", "::1") or ip.startswith("::ffff:127."):
        return "localhost"
    if ip.startswith("100.") or ip.startswith("fd7a:"):   # Tailscale v4 + v6
        return "tailnet"
    if ip in ("0.0.0.0", "::", "*"):
        return "all-interfaces"
    if ip.startswith(("10.", "192.168.", "172.")):
        return "private-lan"
    return "host"


def _browsable(ip: str) -> str:
    if ip in ("0.0.0.0", "*", "::", "::1", "127.0.0.1") or ip.startswith("::ffff:"):
        return "localhost"
    return ip


@router.get("")
@router.get("/")
def list_endpoints(server: Optional[str] = None, db: DBManager = Depends(get_db),
                   _: str = Depends(verify_auth)):
    q = {"server_id": server} if server else {}
    out = []
    upstream_ports = set()

    # 1) Exposure blocks → public/domain endpoints (dedup by host, keep the best).
    by_host = {}
    for cat, via in (("nginx_server_block", "nginx"),
                     ("caddy_site", "caddy"),
                     ("cloudflare_tunnel", "cloudflare_tunnel")):
        for a in db.db.assets.find({**q, "category": cat}):
            m = a.get("metadata", {}) or {}
            host = m.get("server_name") or m.get("hostname") or a.get("name")
            up = m.get("upstream_port")
            if up:
                upstream_ports.add(up)
            if not host or host in ("_", "localhost"):
                continue
            exposed = bool((a.get("health_indicators") or {}).get("internet_exposed")
                           or m.get("internet_exposed"))
            secure = bool(m.get("has_ssl")) or via != "nginx" or exposed
            entry = {
                "url": f"{'https' if secure else 'http'}://{host}", "host": host, "kind": "web",
                "server": a.get("server_id"), "service": a.get("project") or "System",
                "via": via, "upstream": m.get("upstream") or m.get("service")
                          or (f"127.0.0.1:{up}" if up else None),
                "scope": "public" if exposed else "private",
                "access": _exposure_note(via, host, exposed), "root": m.get("root"),
            }
            key = (a.get("server_id"), host)
            prev = by_host.get(key)
            # prefer the block that actually links to a project / is exposed
            if not prev or (entry["service"] != "System" and prev["service"] == "System") \
                    or (entry["scope"] == "public" and prev["scope"] != "public"):
                by_host[key] = entry
    out.extend(by_host.values())

    # 2) Listening ports → standalone UIs / DBs (dedup by port, keep widest address).
    by_port = {}
    for a in db.db.assets.find({**q, "category": "network_port"}):
        m = a.get("metadata", {}) or {}
        if m.get("protocol") not in (None, "tcp"):
            continue
        port = m.get("port")
        if port is None:
            continue
        ip = _ip_of(m.get("local_address") or "")
        scope = _scope_from_addr(ip)
        key = (a.get("server_id"), port)
        prev = by_port.get(key)
        if not prev or _SCOPE_RANK.get(scope, 0) > _SCOPE_RANK.get(prev["scope"], 0):
            by_port[key] = {"asset": a, "m": m, "ip": ip, "scope": scope, "port": port}

    for d in by_port.values():
        a, m, port, scope = d["asset"], d["m"], d["port"], d["scope"]
        rec = _recognize(port)
        fronted = port in upstream_ports
        is_web = bool(rec and rec[2]) or fronted
        if not is_web and not rec:
            continue   # noise: unrecognised non-web port
        out.append({
            "url": f"http://{_browsable(d['ip'])}:{port}" if is_web else None,
            "host": f"{d['ip'] or 'localhost'}:{port}",
            "kind": rec[1] if rec else "web",
            "server": a.get("server_id"),
            "service": a.get("project") or (rec[0] if rec else (m.get("process") or "System")),
            "via": "reverse-proxy backend" if fronted else "direct port",
            "scope": scope, "recognized": rec[0] if rec else None,
            "process": m.get("process"), "access": _port_note(scope, fronted, rec),
        })

    out.sort(key=lambda e: (e["scope"] != "public", e["kind"], e.get("service") or "", e["host"]))
    return {"count": len(out), "endpoints": out}


def _exposure_note(via: str, host: str, exposed: bool) -> str:
    label = {"nginx": "nginx reverse proxy", "caddy": "Caddy",
             "cloudflare_tunnel": "Cloudflare Tunnel (outbound, no open port)"}.get(via, via)
    where = "the public internet" if exposed else "this host"
    return f"Reachable on {where} at {host} via {label}."


def _port_note(scope: str, fronted: bool, rec) -> str:
    if fronted:
        return "Backend for a reverse-proxied site (also directly on this port)."
    notes = {
        "localhost": "Local only — reach via SSH tunnel or `tailscale serve`.",
        "tailnet": "Reachable on your Tailscale tailnet.",
        "all-interfaces": "Listening on all interfaces — reachable on LAN/tailnet (and internet if the firewall allows).",
        "private-lan": "Reachable on the private/VPC network.",
        "host": "Listening locally.",
    }
    base = notes.get(scope, "Listening locally.")
    if rec and rec[1] == "database":
        base = "Database — " + base
    return base
