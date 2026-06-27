"""Secondary -> primary push (outbound, NAT-friendly).

Two outbound flows live here, both initiated by the secondary so nothing has to
reach *into* a NAT'd box:
  - push_to_primary(): ship this server's scan up to the primary (data plane).
  - poll_and_execute(): pull dispatched commands, run them through the local
    guarded actions dispatcher, push results back (control plane).
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


def poll_and_execute(
    primary_url: str,
    join_token: str,
    server_id: str,
    timeout: int = 25,
) -> dict:
    """Pull this server's pending commands from the primary, execute each via the
    existing guarded dispatcher (app.actions.dispatch — so the allow-list and the
    infradocs-v6-* self-protection apply identically), and report results back.

    All requests are outbound (NAT-friendly), mirroring push_to_primary.
    """
    from app import actions as A  # lazy: a secondary needn't import docker to push scans

    base = primary_url.rstrip("/")
    pending = _post_json(
        base + "/api/federation/commands/pending",
        {"server_id": server_id},
        headers={"X-Join-Token": join_token},
        timeout=timeout,
    )
    results = []
    for cmd in pending.get("commands", []):
        cid = cmd.get("command_id")
        asset = cmd.get("asset", {})
        action = cmd.get("action")
        args = cmd.get("args", {}) or {}
        try:
            res = A.dispatch(asset, action, args)
            payload = {
                "server_id": server_id,
                "status": res.status,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "return_code": res.return_code,
                "duration_ms": res.duration_ms,
            }
        except A.SelfActionRefused as e:
            payload = {"server_id": server_id, "status": "refused",
                       "stderr": str(e), "refused_reason": "self_protect"}
        except A.ActionNotAllowed as e:
            payload = {"server_id": server_id, "status": "failed",
                       "stderr": str(e), "refused_reason": "not_allowed"}
        _post_json(
            base + f"/api/federation/commands/{cid}/result",
            payload,
            headers={"X-Join-Token": join_token},
            timeout=timeout,
        )
        results.append({"command_id": cid, "status": payload["status"]})
    return {"executed": len(results), "results": results}


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
