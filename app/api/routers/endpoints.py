"""Unified web/endpoint inventory across the fleet — every reachable UI/service,
how it's exposed, and where it lives. Generic: derives everything from scanned
assets (exposure blocks + listening ports), with no host-specific assumptions.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.api.dependencies import get_db, verify_auth
from app.core.db_manager import DBManager
from app.core.recognize import recognize

router = APIRouter()

# Wider scope = more reachable; we keep the widest address per port.
_SCOPE_RANK = {"public": 6, "all-interfaces": 5, "tailnet": 4, "private-lan": 3,
               "host": 2, "localhost": 1, "unknown": 0, "private": 0}


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
    #    Recognized via container image (docker-published ports) + process, then the
    #    cached AI labels (Tier 2) for anything still unknown.
    port_image = {}
    for c in db.db.assets.find({**q, "category": "docker_container"}):
        cm = c.get("metadata", {}) or {}
        img = cm.get("image") or cm.get("image_name")
        for hp in cm.get("host_ports") or []:
            if img:
                port_image.setdefault(hp, img)
    ai_labels = {r["_id"]: r for r in db.db.ai_labels.find({})}

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
        proc, image = m.get("process"), port_image.get(d["port"])
        rec = recognize(port=port, image=image, process=proc)
        ai_lbl = None
        if not rec:
            sig = ("image:" + image) if image else (
                ("proc:" + proc) if proc and proc not in ("unknown", "docker-proxy")
                else f"port:{port}")
            ai_lbl = ai_labels.get(sig)
        fronted = port in upstream_ports
        kind = rec[1] if rec else (ai_lbl.get("kind") if ai_lbl else "web")
        label = rec[0] if rec else (ai_lbl.get("label") if ai_lbl else None)
        is_web = bool(rec and rec[2]) or fronted or (kind in ("web", "monitoring", "app", "proxy"))
        if not is_web and not rec and not ai_lbl:
            continue   # genuinely unknown non-web port
        out.append({
            "url": f"http://{_browsable(d['ip'])}:{port}" if is_web else None,
            "host": f"{d['ip'] or 'localhost'}:{port}",
            "kind": kind,
            "server": a.get("server_id"),
            "service": a.get("project") or label or (proc or "System"),
            "via": "reverse-proxy backend" if fronted else "direct port",
            "scope": scope, "recognized": label, "ai": bool(ai_lbl),
            "purpose": ai_lbl.get("purpose") if ai_lbl else None,
            "process": proc,
            "access": _port_note(scope, fronted, (label, kind, is_web) if label else None),
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
