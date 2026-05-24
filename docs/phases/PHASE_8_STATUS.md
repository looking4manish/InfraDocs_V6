# Phase 8 — Operational controls: STATUS

**Status:** Complete
**Date:** 2026-05-24
**Tests:** 29 new (16 dispatcher + 13 API) → 118/118 cumulative

## Scope

Make the dashboard actionable. Until now V6 was strictly read-only: it
discovered, correlated, and exposed data through `/api/*`, but you
still had to drop into a shell to actually start/stop/restart things.
Phase 8 adds:

- **Asset-level actions** — `POST /api/assets/{asset_id}/action` with
  `{"action": "...", "args": {...}}`. Allow-listed per category.
- **Application-level actions** — `POST /api/applications/{name}/action`
  fans out to every container + systemd unit attached to the app and
  returns per-asset results.
- **Audit log** — every action attempt (success, failed, refused) is
  recorded in a new `actions_log` collection. Surfaced via
  `GET /api/actions/`.

Out of scope: UI buttons. The endpoints are ready for the frontend to
consume; rendering action buttons in the asset/app detail views ships
in Phase 9.

## Allow-list

| Category | Allowed actions |
|---|---|
| `docker_container` | start, stop, restart, logs |
| `docker_compose` | up, down, restart |
| `systemd_service` | start, stop, restart, logs, status |
| `systemd_timer` | start, stop, restart, status |
| `nginx_server_block` | test, reload |

All other categories (`docker_image`, `docker_volume`, `docker_network`,
`network_port`, `storage_mount`) explicitly have **no** actions — any
attempt returns `403 Forbidden`. Also exposed at
`GET /api/actions/allowed` so the UI can drive button enable/disable
without hard-coding the matrix.

## Safety rails

1. **Self-protection** — any action targeting a unit whose name starts
   with `infradocs-v6-` is refused with `409 Conflict` (and audited
   with `refused_reason: "self_protect"`). Otherwise a UI
   "restart all" on the `InfraDocs_V6` app would kill the API
   mid-request.
2. **Logs cap** — `logs`/`journalctl` calls cap `tail` at 1000 lines
   even if a larger value is requested.
3. **`sudo -n` only** — every privileged action passes `-n` so the
   request fails fast on a missing sudoers entry rather than hanging
   waiting for a TTY password prompt.
4. **Audit-on-refuse** — even when an action is rejected (403, 409),
   the attempt is logged. There's no quiet path past the audit.

## Action result shape

```jsonc
// POST /api/assets/oci:container:abc123/action
// { "action": "restart" }
{
  "asset_id": "oci:container:abc123",
  "action": "restart",
  "status": "success",            // or "failed"
  "return_code": 0,
  "stdout": "restarted openwebui",
  "stderr": "",
  "duration_ms": 421,
  "details": {}
}
```

For application-level actions, the response wraps a list of per-asset
results plus per-asset status values including `"skipped"` (action is
allowed for some categories in the app but not this one — e.g.,
`{"action": "up"}` on an app whose only assets are containers).

## Audit log shape

```jsonc
// GET /api/actions/?asset_id=oci:container:abc123&limit=10
{
  "count": 2,
  "actions": [
    {
      "timestamp": "2026-05-24T18:42:11.220Z",
      "actor": "msinha",
      "asset_id": "oci:container:abc123",
      "asset_name": "openwebui",
      "category": "docker_container",
      "project": "openwebui",
      "action": "restart",
      "args": {},
      "status": "success",
      "return_code": 0,
      "stdout": "<tail 4000 chars>",
      "stderr": "",
      "duration_ms": 421,
      "refused_reason": null
    },
    // ...
  ]
}
```

Filters: `asset_id`, `action`, `actor`, `limit` (1–500, default 50).

## Manual step: install the sudoers file

For systemd and nginx actions to actually succeed, the API user (`msinha`)
needs passwordless sudo for the narrow command set. A sample file lives
at `deploy/sudoers.infradocs`:

```bash
sudo install -m 0440 deploy/sudoers.infradocs /etc/sudoers.d/infradocs
sudo visudo -c -f /etc/sudoers.d/infradocs   # validate
```

Without this, container actions still work (msinha is in the `docker`
group), but `POST` against a `systemd_service` or `nginx_server_block`
asset returns a `failed` status with `sudo: a password is required` in
`stderr`. The dispatcher won't crash — it'll just record the failure.

## To activate against live OCI

```bash
sudo systemctl restart infradocs-v6-api.service
```

(Same drill as Phase 7 — the new `/api/assets/{id}/action`,
`/api/applications/{name}/action`, and `/api/actions/*` routes need an
API restart to come online.)

## Worked example

```bash
# Tail the openwebui container's last 50 lines
curl -s -u msinha:'PASS' \
     -X POST \
     -H 'Content-Type: application/json' \
     -d '{"action":"logs","args":{"tail":50}}' \
     https://infra.ocialwaysfree.site/api/assets/oci:container:abc123/action

# Restart the whole openwebui app (every container + systemd unit)
curl -s -u msinha:'PASS' \
     -X POST \
     -H 'Content-Type: application/json' \
     -d '{"action":"restart"}' \
     https://infra.ocialwaysfree.site/api/applications/openwebui/action

# Look at the last 10 actions on a specific asset
curl -s -u msinha:'PASS' \
     'https://infra.ocialwaysfree.site/api/actions/?asset_id=oci:container:abc123&limit=10'
```

## Test breakdown

| File | Coverage |
|---|---|
| `tests/test_phase8_actions.py` | 16 tests — allow-list enforcement, self-protection (positive + false-positive guard), docker container actions (start / stop / restart / logs with tail cap), docker NotFound handling, systemd command shape (sudo -n systemctl X), journalctl invocation for logs, status's allow_nonzero, nginx -t and -s reload, duration recording. |
| `tests/test_phase8_api.py` | 13 tests — 404/403/409 paths, audit-on-success, audit-on-refuse, application-level fan-out, mixed success/skipped results, action filters, allowed matrix endpoint, auth required. |

Cumulative: **118/118 passing.**

## Bonus: test auth fix

While building 8D, found that hardcoding `AUTH = ("msinha",
"msinha123")` in API tests silently broke the moment you set a real
`INFRADOCS_API_PASSWORD` in `.env`. All three API test files (Phase 3 /
7 / 8) now derive the auth tuple from config + env at module load time:

```python
def _resolve_auth():
    _cfg = load_config(str(ROOT / "config.yml"))
    return (_cfg.auth.username,
            os.environ.get(_cfg.auth.password_env) or _cfg.auth.dev_password)

AUTH = _resolve_auth()
```

So tests pass whether `.env` is set or not.

## Decisions worth remembering

- **One endpoint per scope.** `POST /api/assets/{id}/action` for fine-
  grained control, `POST /api/applications/{name}/action` for whole-app.
  No `start_all`, `stop_all`, `bulk` etc. — the app endpoint already
  fans out and the assets endpoint already targets one thing.
- **Audit even refusals.** A 403 or 409 still writes a row with
  `refused_reason`. Easier to investigate "why didn't that work" later.
- **Self-protect by prefix, not exact match.** Catches future
  `infradocs-v6-worker.service`, `infradocs-v6-scheduler.service`, etc.
  Tested both the positive case (refuses) and the false-positive guard
  (`infradocs.service` is NOT protected).
- **No allow-list for `docker_image`/`docker_volume`/`docker_network`/
  `network_port`/`storage_mount` is intentional.** Phase 9 might add
  `inspect` or similar for read-only metadata, but anything destructive
  (prune, delete) requires a separate explicit decision.

## Next: Phase 9 — UI polish + hardening

- Action buttons on the asset detail view + app detail view (driven by
  `/api/actions/allowed`).
- Inline log viewer for the `logs` action result.
- Frontend audit-trail view consuming `/api/actions/`.
- Carry-over from earlier phases: retire the leftover `:5173` dev
  server, ship `deploy/build.sh`, frontend automated tests.
