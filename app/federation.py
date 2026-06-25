"""Secondary -> primary push (outbound, NAT-friendly)."""

import json
import urllib.request
from typing import List


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
