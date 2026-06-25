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
    5000: ("web app", "web", True), 8443: ("HTTPS-alt", "web", True),
    9090: ("Prometheus / Cockpit", "monitoring", True), 9100: ("node-exporter", "monitoring", True),
    3001: ("Grafana", "monitoring", True), 9091: ("Pushgateway", "monitoring", True),
    5601: ("Kibana", "monitoring", True), 9093: ("Alertmanager", "monitoring", True),
    27017: ("MongoDB", "database", False), 27018: ("MongoDB", "database", False),
    27028: ("MongoDB (mongot)", "database", False),
    5432: ("PostgreSQL", "database", False), 3306: ("MySQL", "database", False),
    6379: ("Redis", "database", False), 9200: ("Elasticsearch", "database", True),
    8086: ("InfluxDB", "database", True), 2019: ("Caddy admin API", "infra", False),
}


def _recognize(port: Optional[int]):
    return KNOWN_PORTS.get(port)


def _scope_from_addr(addr: Optional[str]) -> str:
    if not addr:
        return "unknown"
    if addr.startswith("127.") or addr == "::1":
        return "localhost"
    if addr.startswith("100."):       # CGNAT / Tailscale range
        return "tailnet"
    if addr in ("0.0.0.0", "::", "*"):
        return "all-interfaces"
    if addr.startswith(("10.", "192.168.", "172.")):
        return "private-lan"
    return "host"


@router.get("")
@router.get("/")
def list_endpoints(server: Optional[str] = None, db: DBManager = Depends(get_db),
                   _: str = Depends(verify_auth)):
    q = {"server_id": server} if server else {}
    out = []
    upstream_ports = set()  # ports fronted by a reverse proxy / tunnel

    # 1) Exposure blocks → public/domain endpoints.
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
            url = f"{'https' if secure else 'http'}://{host}"
            out.append({
                "url": url, "host": host, "kind": "web",
                "server": a.get("server_id"), "service": a.get("project") or "System",
                "via": via, "upstream": m.get("upstream") or m.get("service")
                          or (f"127.0.0.1:{up}" if up else None),
                "scope": "public" if exposed else "private",
                "access": _exposure_note(via, host, exposed),
                "root": m.get("root"),
            })

    # 2) Listening ports → standalone local UIs / DBs not already fronted by a domain.
    for a in db.db.assets.find({**q, "category": "network_port"}):
        m = a.get("metadata", {}) or {}
        if m.get("protocol") not in (None, "tcp"):
            continue
        port = m.get("port")
        rec = _recognize(port)
        fronted = port in upstream_ports
        is_web = bool(rec and rec[2]) or fronted
        # Skip the noise: non-web, unrecognised, not fronted.
        if not is_web and not rec:
            continue
        addr = m.get("local_address")
        scope = _scope_from_addr(addr)
        out.append({
            "url": f"http://{addr or 'localhost'}:{port}" if (is_web) else None,
            "host": f"{addr or 'localhost'}:{port}",
            "kind": rec[1] if rec else "web",
            "server": a.get("server_id"),
            "service": a.get("project") or (rec[0] if rec else m.get("process") or "System"),
            "via": "reverse-proxy backend" if fronted else "direct port",
            "upstream": None,
            "scope": scope,
            "recognized": rec[0] if rec else None,
            "process": m.get("process"),
            "access": _port_note(scope, fronted, rec),
        })

    out.sort(key=lambda e: (e["scope"] != "public", e.get("service") or "", e["host"]))
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
    }
    base = notes.get(scope, "Listening locally.")
    if rec and rec[1] == "database":
        base = "Database — " + base
    return base
