# Phase 1 — Foundation: STATUS

**Status:** Complete
**Date:** 2026-05-23
**Tests:** 13/13 passing, 0 warnings

## Scope

Build the foundation layer for V6: directory layout, dependencies, config loader, logger, MongoDB manager, project detector. No scanners or API yet.

## Deliverables

| File | Purpose |
|---|---|
| `app/core/logger.py` | Structured JSON logger (console + file) |
| `app/core/config_loader.py` | Pydantic-validated YAML loader, `.env` integration |
| `app/core/db_manager.py` | Single-database MongoDB client (URI-based) |
| `app/core/project_detector.py` | Project ownership detection (no false projects from service names) |
| `config.yml` | OCI-only configuration; `mongodb.uri_env: INFRADOCS_MONGO_URI` |
| `requirements.txt` | Python deps (fastapi, pymongo, pydantic, python-dotenv, etc.) |
| `.env.example` | Template; real `.env` is gitignored |
| `.gitignore` | Excludes venv, logs, `.env`, build artifacts |
| `tests/test_phase1.py` | 13 smoke tests for the above |

## Key decisions vs V5

- **Single database** (`infradocs`) on the shared 3-node replica set (biwi primary, OCI + N150 secondaries). V5's per-server DB pattern (`infradocs_oci`, `infradocs_n150`) is dropped.
- **`server_id="oci"`** is kept as a constant field on every document for forward-compatibility — when distributed scanning returns post-V6, no schema migration is needed.
- **Connection URI loaded from env** (`INFRADOCS_MONGO_URI` in `.env`); never committed to git.
- **No `peer_servers`, no sync config, no rsync paths** in `config.yml` — distributed concerns deferred.
- **ProjectDetector** ported faithfully from V5's post-Phase-7A fix: only paths under `/home/msinha/projects/*` get project names; everything else is `"System"`. The V5 false-project regression (`cloud-init.service` → "Cloud") is explicitly tested.
- **Domain mapping** updated: `infra.*` now points to `InfraDocs_V6` (was `InfraDocs_V5`).

## Tests

```
tests/test_phase1.py::test_imports                                       PASSED
tests/test_phase1.py::test_config_loads                                  PASSED
tests/test_phase1.py::test_mongodb_uri_resolves_from_env                 PASSED
tests/test_phase1.py::test_mongodb_uri_missing_raises                    PASSED
tests/test_phase1.py::test_logger_setup                                  PASSED
tests/test_phase1.py::test_project_detector_scans_real_projects          PASSED
tests/test_phase1.py::test_project_detector_path_resolution              PASSED
tests/test_phase1.py::test_project_detector_rejects_service_name_inference PASSED
tests/test_phase1.py::test_project_detector_container_label              PASSED
tests/test_phase1.py::test_project_detector_domain_mapping               PASSED
tests/test_phase1.py::test_mongodb_connection                            PASSED
tests/test_phase1.py::test_db_manager_asset_round_trip                   PASSED
tests/test_phase1.py::test_replica_set_primary_reachable                 PASSED
```

## Bugs found & fixed during Phase 1

1. **pip resolution conflict** — `pytest==8.0.0` pinned hard against `pytest-asyncio==0.23.4`. Loosened to `pytest>=8,<9` and `pytest-asyncio>=0.23`.
2. **Mongo auth blocker** — local mongod runs as part of a 3-node replica set with `keyFile` auth. Rewired `DBManager` to take a URI string instead of `host:port`, and loader pulls the URI from `.env`.
3. **`load_dotenv` masking monkeypatch** — the "missing URI" test failed because `load_config` reloads `.env` each call. Fixed by isolating the test with a tmp_path config so no sibling `.env` is loaded.
4. **`datetime.utcnow()` deprecation** in Python 3.12 — switched to `datetime.now(timezone.utc)` in `logger.py` and `db_manager.py`.

## Open items / notes for later phases

- Stale `infradocs_n150` DB exists in the RS from V5's run. Left alone for now; will decide whether to drop or migrate when distributed support returns.
- Sample Atlas data (`sample_*`, `shopfast*`) also present in the RS — unrelated, ignore.
- `app/templates/` exists empty (from yesterday's V6 scaffold). Not used yet; leaving in place — Phase 4 may or may not use Jinja for any server-side rendering.

## Next: Phase 2 — Scanners

Port `BaseScanner` + 6 scanner classes from V5, all wired to `ProjectDetector` and the new `DBManager`. Build `agent.py` orchestrator.
