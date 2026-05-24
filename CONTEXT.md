# InfraDocs V6 — Project Context (for fresh Claude sessions)

This file is the single-page brief a new Claude session should read to be productive on this repo without re-deriving everything. Keep it concise; deep details live in `docs/`.

---

## What this is

A single-host infrastructure dashboard for OCI. Scans → correlates → exposes → visualizes → **acts on** everything running on the box. Live at https://infra.ocialwaysfree.site/.

Rewrite of V5 (which distributed scanning across multiple hosts and turned into a debugging mess). V6 deliberately targets one host (production-quality OCI-only); multi-host returns post-V6.

## Where things live

```
/home/msinha/projects/InfraDocs_V6/
├── app/
│   ├── core/                       config, db_manager, project_detector, logger
│   ├── scanners/                   one per category: docker, compose, systemd, nginx, port, storage
│   ├── correlator.py               flat assets → application documents (project + System buckets)
│   ├── ports_registry.py           Phase 7B
│   ├── storage_registry.py         Phase 7C
│   ├── actions.py                  Phase 8 dispatcher
│   ├── agent.py                    CLI: python -m app.agent scan
│   └── api/
│       ├── main.py                 FastAPI app + router includes
│       ├── dependencies.py         auth, db, config
│       └── routers/                health, assets, projects, applications,
│                                   ports, storage, scans, actions
├── frontend/                       React 19 + Vite 8 + Tailwind 3 + React Query 5
├── deploy/                         systemd unit, nginx vhost, install scripts, sudoers.infradocs
├── docs/
│   ├── ARCHITECTURE.md             read-me-first for any structural change
│   ├── DEVELOPMENT.md
│   ├── DEPLOY.md
│   └── phases/PHASE_{1..8}_STATUS.md    build journal — what landed, why, gotchas
├── tests/                          118 tests across phases 1-8
├── config.yml
├── .env                            INFRADOCS_MONGO_URI + INFRADOCS_API_PASSWORD (gitignored)
├── README.md
└── CONTEXT.md                      this file
```

## Status (as of 2026-05-24)

| Phase | What | Status |
|---|---|---|
| 1 | Foundation (config, db, project_detector) | ✅ |
| 2 | Six scanners (docker, compose, systemd, nginx, port, storage) | ✅ |
| 3 | FastAPI API on :8004 with HTTP Basic auth | ✅ |
| 4 | React+Vite frontend (Dashboard, Projects, Assets, Scans) | ✅ |
| 5 | Scanner enrichment + correlator (application documents) | ✅ |
| 6 | Live on internet via nginx + Cloudflare + LE wildcard cert | ✅ |
| 7 | Project/System ownership + Ports registry + Storage registry | ✅ |
| 8 | Operational controls (start/stop/restart/logs + audit log) | ✅ |
| 9A | Frontend extension: Applications/Ports/Storage/Actions pages + action buttons | ✅ |
| 9B | UI polish, frontend tests, hardening | pending |

## Data model — the 30-second mental model

Every asset (container, image, volume, network, compose file, nginx server block, systemd unit, listening port, mount) lands in **exactly one bucket**:

- a `~/projects/<name>` project bucket (one per subfolder of `/home/msinha/projects`), OR
- the single `System` bucket (everything that can't be tied to a project folder)

This invariant is enforced by `correlator.py` and checked every scan by `audit_ownership()`. No orphans, no third bucket, no null project fields.

Collections in Mongo (db: `infradocs`):

| Collection | What | Unique key |
|---|---|---|
| `assets` | Flat output of all scanners | `(category, asset_id)` |
| `applications` | Correlated docs, one per project bucket + System | `application_id` |
| `ports` | Phase 7B registry (evidence-based, deduped per port+proto) | `port_id` |
| `storage` | Phase 7C registry (mounts + volumes + project trees + binds) | `storage_id` |
| `actions_log` | Phase 8 audit (every action attempt, including refusals) | — |
| `scan_logs` | One row per scan with summary stats | — |
| `projects` | Currently unused (legacy from V5) | `project_name` |

## API surface

All under `/api/*`. Auth: HTTP Basic, username `msinha`, password from `INFRADOCS_API_PASSWORD` env var (falls back to `dev_password` in `config.yml` if env is unset). The `/` and `/api/health` routes are public.

```
GET  /                               name + version (public)
GET  /api/health                     mongo ping (public)

GET  /api/assets/                    filters: category, project, status
GET  /api/assets/categories          counts per category
GET  /api/assets/{asset_id}          one asset

GET  /api/projects/list              counts + health score per project
GET  /api/projects/{name}            full asset list for a project

GET  /api/applications/list          correlated app docs
GET  /api/applications/{name}        one app doc

GET  /api/ports/                     filters: state, project, port_min, port_max
GET  /api/ports/summary              counts by state + by owner
GET  /api/ports/probe?range=X-Y      live ss snapshot, NOT persisted

GET  /api/storage/                   filters: kind, project
GET  /api/storage/summary            counts + size_bytes by kind + by owner

GET  /api/scans/                     recent scan logs
GET  /api/scans/{scan_id}            one scan
POST /api/scans/trigger              202 + background scan

POST /api/assets/{asset_id}/action          {"action":"...", "args":{...}}
POST /api/applications/{name}/action        fans out to all assets in the app
GET  /api/actions/                          audit log; filters: asset_id, action, actor, limit
GET  /api/actions/allowed                   per-category action allow-list
```

### Action dispatcher allow-list (Phase 8)

| Category | Allowed actions |
|---|---|
| `docker_container` | start, stop, restart, logs |
| `docker_compose` | up, down, restart |
| `systemd_service` | start, stop, restart, status, logs |
| `systemd_timer` | start, stop, restart, status |
| `nginx_server_block` | test, reload |

All other categories explicitly have no actions → 403. Self-protection: any `infradocs-v6-*` unit → 409. Audit log records every attempt (success, failed, refused).

## Frontend — what exists right now (Phase 4 baseline)

Stack: React 19 + Vite 8 + Tailwind 3 + React Router 7 + TanStack Query 5 + axios.

Visual language (don't break this when adding pages):
- Dark theme. Palette in `tailwind.config.js`: `bg-base`/`bg-panel`/`bg-card`/`bg-hover`, `accent` (#3b82f6).
- Sidebar + header layout; main content scrolls.
- Cards: `bg-bg-card border border-bg-hover rounded-lg p-4`.
- Labels: `text-xs uppercase tracking-wide text-slate-400`.
- Stat values: `text-2xl font-semibold`.
- Active nav: `bg-accent/20 text-accent`.

Pages (Phase 4 + 9A):
- Dashboard (`/`) — hero cards + applications list + recent actions feed + categories strip
- Applications (`/applications`, `/applications/:name`) — card grid + rich detail with action buttons
- Projects (`/projects`, `/projects/:name`) — simpler legacy view from /api/projects
- Ports (`/ports`) — registry table + filters + live `ss` probe widget
- Storage (`/storage`) — by-owner bar chart + kind tabs + table with mount usage bars
- Actions (`/actions`) — audit log with expandable rows showing stdout/stderr
- Assets (`/assets`) — flat list with category/project/status filters
- Scans (`/scans`) — history table + trigger button

Shared components: `AppCard`, `ActionButton` (with confirm + output modal), `StatePill`, `UsageBar`, `Bytes/formatBytes`.

axios client at `frontend/src/api/client.js`:
- Reads creds from `localStorage` (`ifd_user`, `ifd_pass`).
- No hardcoded password fallback (removed post-Phase-8). Empty creds → 401 → browser shows native auth prompt.
- 401 response wipes stored `ifd_pass` so a wrong cached password doesn't silently loop.

## Conventions

- **Add a scanner:** subclass `BaseScanner`, emit dicts via `self.create_asset(...)` with an explicit `project=`. Register in `app/scanners/registry.py`. Every asset MUST get a project field (project folder name or `"System"`).
- **Add an API endpoint:** new file in `app/api/routers/`, include in `app/api/main.py`. Always depend on `verify_auth` unless the route is intentionally public.
- **Add a DB collection:** add `replace_X` / `get_X` methods on `DBManager`; create indexes in `DBManager.create_indexes()` (called at API startup and from the agent).
- **Tests:** mirror file path under `tests/`. API tests use TestClient + dependency override pattern from `test_phase3_api.py`. Auth derived from env+config via `_resolve_auth()` (don't hardcode credentials in tests — they'll silently break the moment a real password is set in .env).
- **Commits:** small, per sub-task. Each phase is split into A/B/C/D commits when reasonable. Co-author footer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- **Memory:** see [memory README](#) — autonomous mode + data-model invariant memories live in `~/.claude/projects/-home-msinha-projects/memory/`.

## How to develop / run

```bash
# One-time
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env  # then set INFRADOCS_MONGO_URI

# Scan + populate DB
python -m app.agent scan --summary

# Run the API locally (different port from prod 8004)
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8005

# Frontend dev (proxies /api/* to :8004)
cd frontend && npm install && npm run dev

# Frontend prod build → nginx serves frontend/dist/
cd frontend && npm run build

# Tests
python -m pytest tests/ -v

# Restart live API to pick up code changes
sudo systemctl restart infradocs-v6-api.service
```

## Live deploy details

| What | Where |
|---|---|
| API | `infradocs-v6-api.service` systemd unit, runs as `msinha`, port 8004, EnvironmentFile loads `.env` |
| Nginx vhost | `/etc/nginx/sites-enabled/infra.ocialwaysfree.site` → serves `frontend/dist/` static + proxies `/api/*` to `127.0.0.1:8004` |
| Cert | `/etc/letsencrypt/live/ocialwaysfree.site/*` (wildcard) |
| DNS | Cloudflare-fronted — `infra.ocialwaysfree.site` → 104.21.95.155 (CF edge) |
| Sudoers (for Phase 8 systemd/nginx actions) | `/etc/sudoers.d/infradocs` (install from `deploy/sudoers.infradocs`) |

## Known open items

- Frontend has no automated tests yet (Phase 9 polish).
- The `frontend/dist/` build is manual (`npm run build`); a `deploy/build.sh` would be a nice-to-have.
- The vite dev server on `:5173` may still be running from Phase 4 testing — harmless but should be retired.
- `INFRADOCS_API_PASSWORD` is now set (no longer the dev default). Don't commit it.
- Some `~/projects/*` subfolders (`claude`, `RaveUploader`) exist but have no live runtime assets — they appear as empty application docs intentionally so the dashboard sees the complete project list.

## What changed recently — read in order

1. `docs/phases/PHASE_7_STATUS.md` — ownership invariant + ports + storage registries
2. `docs/phases/PHASE_8_STATUS.md` — action dispatcher + audit log + endpoints
3. Frontend `client.js` — removed hardcoded `msinha123` fallback
4. Test files — `AUTH = _resolve_auth()` pattern (so env-set password doesn't break the suite)
5. `docs/phases/PHASE_9A_FRONTEND_STATUS.md` — five new pages, action buttons, dashboard refresh
6. `frontend/vite.config.js` — `build.assetsDir = "static"` (fixed `/assets` route 301 caused by dist/assets/ shadowing the SPA route — present since Phase 6)
