"""Secondary <-> primary HTTP helpers for the direct (mesh) federation model.

Every node is directly reachable on the tailnet, so these are plain point-to-point
calls (no queue):
  - push_to_primary(): ship this server's scan to the primary (data plane).
  - ping_node() / enroll_with_primary(): the bidirectional reachability handshake
    used at enroll time (added with the direct model).
"""

import json
import urllib.request
from typing import List, Optional


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
    timeout: int = 10,
) -> dict:
    """Secondary-side of the bidirectional reachability handshake.

    POSTs to the primary's /enroll with this node's own advertised address. The POST
    arriving proves secondary->primary; the primary then connects BACK to
    advertise_url and reports whether primary->secondary worked. Returns a uniform
    result; a primary we can't even reach is reported as secondary->primary = False
    (rather than raising), so the wizard can show a clean per-direction verdict.
    """
    base = primary_url.rstrip("/")
    try:
        res = _post_json(
            base + "/api/federation/enroll",
            {"server_id": server_id, "secondary_url": advertise_url, "join_token": join_token},
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 — any transport error means we couldn't reach the primary
        return {
            "ok": False,
            "directions": {"secondary_to_primary": False, "primary_to_secondary": None},
            "reason": f"could not reach the primary at {base}: {e}",
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
