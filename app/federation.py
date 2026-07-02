"""Secondary <-> primary HTTP helpers for the direct (mesh) federation model.

Every node is directly reachable on the tailnet, so these are plain point-to-point
calls (no queue):
  - push_to_primary(): ship this server's scan to the primary (data plane).
  - ping_node() / enroll_with_primary(): the bidirectional reachability handshake
    used at enroll time (added with the direct model).
"""

import json
import urllib.error
import urllib.request
from typing import List, Optional
from urllib.parse import urlsplit

from app.cli_install import normalize_url


def probe_failure_reason(url, exc) -> str:
    """Translate a reachability-probe exception into a NAMED, human reason so the UI
    never sees a raw 'tlsv1 alert internal error'."""
    msg = str(exc).lower()
    u = url if "://" in url else "http://" + url
    try:
        parts = urlsplit(u); has_port = parts.port is not None; scheme = parts.scheme
    except ValueError:
        has_port, scheme = True, "http"
    if any(t in msg for t in ("tlsv1", "ssl", "wrong version number", "unknown protocol",
                              "alert internal error", "record layer", "certificate", "eof occurred")):
        if (not has_port) or scheme == "https":
            return (f"missing-port/wrong-scheme: {url} has no explicit port (or uses https), so the "
                    f"probe hit TLS on 443 — store an explicit http://ADDR:PORT (e.g. :8081)")
        return f"wrong-scheme: {url} answered TLS where plain http was expected — check scheme/port"
    if any(t in msg for t in ("refused", "timed out", "timeout", "no route", "unreachable",
                              "could not connect", "reset by peer", "name or service not known",
                              "temporary failure in name resolution")):
        return (f"unreachable: {url} did not respond (firewall or wrong address; if this is a public "
                f"IP, open the port in the cloud firewall) — firewall-likely")
    return f"unreachable: could not reach {url} ({type(exc).__name__})"


def _post_json(url: str, body: dict, headers: Optional[dict] = None, timeout: int = 25) -> dict:
    data = json.dumps(body, default=str).encode()  # datetimes / ObjectIds -> strings
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method="POST", headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode())


def _get_json(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode())


def ping_node(node_url: str, timeout: int = 8) -> dict:
    """GET a node's /api/federation/ping (its identity + lease view). Raises on any
    failure to reach it — callers treat an exception as 'unreachable'."""
    return _get_json(node_url.rstrip("/") + "/api/federation/ping", timeout=timeout)


def enroll_with_primary(
    primary_url: str,
    advertise_url: str,
    join_token: str,
    server_id: str,
    priority: int,
    timeout: int = 10,
) -> dict:
    """Secondary-side of the bidirectional reachability handshake.

    POSTs to the primary's /enroll with this node's own advertised address + desired
    priority. The POST arriving proves secondary->primary; the primary then connects
    BACK to advertise_url and reports whether primary->secondary worked (and rejects a
    duplicate priority). A primary we can't even reach is reported as
    secondary->primary = False (rather than raising), so the wizard shows a clean verdict.
    """
    primary_url = normalize_url(primary_url)
    advertise_url = normalize_url(advertise_url)
    base = primary_url.rstrip("/")
    try:
        res = _post_json(
            base + "/api/federation/enroll",
            {"server_id": server_id, "secondary_url": advertise_url,
             "join_token": join_token, "priority": priority},
            timeout=timeout,
        )
    except urllib.error.HTTPError as e:
        # The primary RESPONDED (so secondary->primary works) but rejected enrollment —
        # e.g. a duplicate priority (409) or a bad token (401). Surface its reason.
        try:
            detail = json.loads(e.read().decode()).get("detail")
        except Exception:  # noqa: BLE001
            detail = None
        return {
            "ok": False,
            "directions": {"secondary_to_primary": True, "primary_to_secondary": None},
            "reason": detail or f"primary rejected enrollment (HTTP {e.code})",
        }
    except Exception as e:  # noqa: BLE001 — any transport error means we couldn't reach the primary
        return {
            "ok": False,
            "directions": {"secondary_to_primary": False, "primary_to_secondary": None},
            "reason": "secondary→primary unreachable: " + probe_failure_reason(base, e),
        }
    return res


def push_to_primary(
    primary_url: str,
    join_token: str,
    server_id: str,
    assets: List[dict],
    applications: List[dict],
    timeout: int = 25,
) -> dict:
    """POST this server's scan results to the primary's ingest endpoint."""
    payload = json.dumps(
        {"server_id": server_id, "assets": assets, "applications": applications},
        default=str,  # datetimes / ObjectIds -> strings
    ).encode()
    req = urllib.request.Request(
        primary_url.rstrip("/") + "/api/federation/ingest",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "X-Join-Token": join_token},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode())
