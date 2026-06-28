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
