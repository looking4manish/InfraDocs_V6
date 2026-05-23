# Phase 3 — API: STATUS

**Status:** Complete
**Date:** 2026-05-23
**Tests:** 16/16 Phase 3, 39/39 cumulative

## Scope

FastAPI service on `:8004` exposing read endpoints over the assets/projects/scans collections plus a write endpoint that kicks off a scan in the background. HTTP Basic Auth gates every endpoint except `/api/health` and `/`.

## Deliverables

| File | Purpose |
|---|---|
| `app/api/main.py` | FastAPI app, CORS, lifespan that opens DB + creates indexes |
| `app/api/dependencies.py` | `get_config`, `get_db`, `verify_auth` (constant-time compare) |
| `app/api/routers/health.py` | `GET /api/health` — public, returns mongo ping |
| `app/api/routers/assets.py` | `GET /api/assets/`, `/categories`, `/{asset_id}` |
| `app/api/routers/projects.py` | `GET /api/projects/list`, `/{project_name}` with health score |
| `app/api/routers/scans.py` | `POST /api/scans/trigger` (202 + background task), `GET /api/scans/`, `/{scan_id}` |
| `tests/test_phase3_api.py` | 16 tests using FastAPI TestClient + dependency overrides |

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/` | none | name + version |
| GET | `/api/health` | none | mongo ping |
| GET | `/api/assets/` | basic | filters: `category`, `project`, `status`, `limit` |
| GET | `/api/assets/categories` | basic | category → count |
| GET | `/api/assets/{asset_id}` | basic | 404 if missing |
| GET | `/api/projects/list` | basic | per-project asset count, categories, health score |
| GET | `/api/projects/{name}` | basic | full asset list for the project |
| POST | `/api/scans/trigger` | basic | 202, returns `scan_id`; scan runs as BackgroundTask |
| GET | `/api/scans/` | basic | recent scan logs |
| GET | `/api/scans/{scan_id}` | basic | individual scan status |

## Live boot verification

```
$ curl localhost:8004/api/health
{"status":"ok","mongo":{"ok":true}}

$ curl -u msinha:msinha123 localhost:8004/api/projects/list
  InfraDocs_V6 - 1 assets, health 90
  OCI_Dashboard - 4 assets, health 90
  System - 234 assets, health 72
  openwebui - 4 assets, health 90
  raveuploader_rws - 3 assets, health 90

$ curl -u msinha:msinha123 -X POST localhost:8004/api/scans/trigger
{"scan_id":"92ce9f6cb0de4e4ebde84341425c5eb0","status":"queued"}
# 10s later, /api/scans/{id} returns status=success, total_assets=246
```

## Decisions

- **Background scans via FastAPI BackgroundTasks** — the trigger returns immediately with `202 Accepted` so the UI doesn't block. Scan progress is captured in `db.scan_logs` keyed by `scan_id`.
- **Constant-time auth comparison** (`secrets.compare_digest`) to avoid timing side-channels.
- **CORS open (`*`) for now** — fine because every endpoint requires Basic Auth. Will tighten in Phase 6 when the frontend has a known origin.
- **Auth password resolution order:** `INFRADOCS_API_PASSWORD` env var → `cfg.auth.dev_password`. Production deploys must set the env var.
- **Project health score formula:** average of per-asset scores derived from category-specific signals (storage `100 - usage_percent`, container `running + restarts==0`, systemd `active`, others `90` default). Crude but useful as a first signal.
- **No `servers` router** — V6 is single-host. Reintroducing distributed support post-V6 will add the router back.

## Tests

```
tests/test_phase3_api.py::test_root                                  PASSED
tests/test_phase3_api.py::test_health                                PASSED
tests/test_phase3_api.py::test_auth_required                         PASSED
tests/test_phase3_api.py::test_wrong_password                        PASSED
tests/test_phase3_api.py::test_list_assets                           PASSED
tests/test_phase3_api.py::test_list_assets_filter_by_category        PASSED
tests/test_phase3_api.py::test_list_assets_filter_by_project         PASSED
tests/test_phase3_api.py::test_assets_categories                     PASSED
tests/test_phase3_api.py::test_get_asset_by_id                       PASSED
tests/test_phase3_api.py::test_get_asset_404                         PASSED
tests/test_phase3_api.py::test_projects_list                         PASSED
tests/test_phase3_api.py::test_project_detail                        PASSED
tests/test_phase3_api.py::test_project_detail_404                    PASSED
tests/test_phase3_api.py::test_scan_trigger_returns_queued           PASSED
tests/test_phase3_api.py::test_list_scans_empty                      PASSED
tests/test_phase3_api.py::test_scan_get_404                          PASSED
```

## Notes for Phase 4 (frontend)

- API base: `http://localhost:8004` in dev (via Vite proxy) or `https://<host>/api/` in prod (via nginx).
- All API calls need `Authorization: Basic ...` header (default creds `msinha:msinha123` in dev).
- Trigger pattern: `POST /api/scans/trigger` → poll `GET /api/scans/{scan_id}` until `status: success|failed`.
- `agent.py` writes scan_logs without a `scan_id` field. API-triggered scans include `scan_id`. Frontend should handle both. (Cleanup: agent.py could also generate a scan_id — defer to Phase 5/6.)

## Next: Phase 4 — Frontend

React + Vite, dark theme, sidebar + header (no server selector), Dashboard / Projects / Assets pages. User UI-tests this phase.
