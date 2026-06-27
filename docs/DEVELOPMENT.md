# Development guide

This covers the day-to-day developer flow. For why-it-works-this-way, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Prerequisites

- Python 3.12+
- Node 20+ / npm 10+
- MongoDB (single instance, replica set, or Atlas — anything with a `mongodb://` URI works)
- Linux (the scanners shell out to `systemctl`, `ss`, `df`; macOS/Windows aren't supported)
- Optional but recommended: `nginx`, `docker` (so all scanners have data to find)

## First-time setup

```bash
git clone <repo> && cd InfraDocs_V6

# Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
$EDITOR .env
# Set:
#   INFRADOCS_MONGO_URI=mongodb://localhost:27017/   # or your replica-set URI
#   INFRADOCS_AUTH_DISABLED=1                         # optional: skip auth entirely in local dev

# Frontend
cd frontend
npm install
cd ..
```

## Common loops

### Run a one-shot scan and inspect the data

```bash
source venv/bin/activate
python -m app.agent scan --summary
```

The agent runs all enabled scanners (docker, compose, systemd, port, storage, nginx, caddy,
cloudflared, certs, cron — see `enabled_scanners` in `config.yml`), writes raw assets, then
runs the correlator and writes applications. `--summary` prints by-category and by-project
counts at the end.

### Start the API

```bash
source venv/bin/activate
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8004
```

Hit `http://localhost:8004/docs` for the auto-generated OpenAPI UI. Auth: a default `admin`
user is seeded (`admin` / `Changeme001`, forced password change on first login); the API
issues a session token used as `Authorization: Bearer`. For a frictionless local loop, set
`INFRADOCS_AUTH_DISABLED=1` in `.env` to bypass auth. `verify_auth` also accepts HTTP Basic
against the DB user or a config-credential fallback. See `app/auth.py` +
`app/api/routers/auth.py`.

### Start the frontend dev server

```bash
cd frontend
npm run dev
# → http://localhost:5173/
```

Vite proxies `/api/*` to `http://127.0.0.1:8004`, so the API must already be running. Hot module reload is on.

### Trigger a scan from the running API

```bash
# with auth disabled in dev:
curl -X POST http://localhost:8004/api/scans/trigger
# or with a session token:
curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8004/api/scans/trigger
# returns {"scan_id":"...","status":"queued"}; scan runs as a BackgroundTask
```

Or click "Run scan" in the UI — same effect.

### Building the frontend (mind the live-dist trap)

The live OCI box serves `frontend/dist/` via nginx, so a bare `npm run build` /
`npx vite build` in the repo **instantly changes production**. When you only want to check
that the frontend compiles, build to a throwaway dir:

```bash
cd frontend && npx vite build --outDir /tmp/ifd-check
```

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Tests live under `tests/` (one file per area). The main ones:

- `test_phase1.py` — core utilities, config loader, project detector, DB connection
- `test_phase2_scanners.py` — scanner integration tests against the local host
- `test_phase3_api.py` / `test_phase7_api.py` / `test_phase8_api.py` — FastAPI endpoints
- `test_phase5_correlator.py` / `test_v7_phase1_correlator.py` — correlation logic
- `test_phase7_ports.py` / `test_phase7_storage.py` — registries
- `test_phase8_actions.py` — action dispatcher + allow-list
- `test_auth.py` · `test_setup.py` · `test_federation.py` — auth, wizard, federation
- `test_exposure_detectors.py` · `test_nginx_attribution.py` · `test_cert_scanner.py` ·
  `test_cron_scanner.py` — newer scanners + exposure detectors
- `test_blast_radius.py` · `test_teardown.py` · `test_project_discovery.py`

Tests that require MongoDB are auto-skipped if `INFRADOCS_MONGO_URI` is unset, so
`pytest tests/` is safe even without Mongo configured. Run a single file:
`pytest tests/test_auth.py -v`.

## Project layout (developer view)

```
app/
├── agent.py              # CLI entry — `python -m app.agent scan`
├── correlator.py         # raw assets → application documents (+ links[] evidence)
├── actions.py            # action dispatcher + allow-list
├── ai.py                 # optional LLM layer (label_service + fleet_insights)
├── auth.py               # bcrypt + DB session tokens
├── federation.py         # primary mint-token / secondary outbound ingest
├── blast_radius.py       # teardown blast-radius computation
├── teardown.py           # guarded project teardown
├── ports_registry.py · storage_registry.py
├── core/
│   ├── config_loader.py  # Pydantic models + load_dotenv (scan_roots, etc.)
│   ├── db_manager.py     # MongoDB wrapper, single DB
│   ├── project_detector.py   # multi-root discovery + path→project attribution
│   ├── recognize.py      # deterministic service recognition (Tier 1)
│   ├── hostpath.py       # read host configs through the /host mount (container)
│   └── logger.py
├── scanners/
│   ├── base.py           # BaseScanner ABC
│   ├── systemd.py · docker.py · compose.py · port.py · storage.py
│   ├── nginx.py          # parses sites-enabled (brace-aware) + captures `root`
│   ├── caddy.py · cloudflared.py     # exposure detectors (via hostpath)
│   ├── certs.py · cron.py
│   └── registry.py       # name → class map
└── api/
    ├── main.py           # FastAPI app, lifespan (seeds admin), CORS, router includes
    ├── dependencies.py   # get_db, verify_auth (Bearer | Basic | disabled)
    └── routers/
        ├── auth.py · setup.py · federation.py        # auth, wizard, multi-server
        ├── endpoints.py · ai.py                       # Web tab, AI layer
        ├── assets.py · applications.py · projects.py
        ├── ports.py · storage.py · scans.py · actions.py · health.py
```

## Conventions

- **Asset shape**: every asset has `server_id`, `category`, `asset_id`, `name`, `status`, `project`, `metadata`, `scanner`, `discovered_at`. Add new fields to `metadata`, not the top level.
- **Asset IDs** are deterministic and must be unique across one scan — V6 has fixed bugs where IPv4+IPv6 ports or HTTP+HTTPS server blocks for the same name collided on upsert. When adding a new asset type, sanity-check uniqueness.
- **`project` field**: only paths under `projects_root/<X>/` get a project name; never infer from a string prefix. This is enforced by passing every project decision through `ProjectDetector`.
- **Env values are dropped** — capture key names only. Storing secrets in the documentation DB defeats the point of secrets.
- **Errors stay inside the scanner** — every `scan()` returns a list and uses `self.add_error()` for partial failures; the orchestrator never crashes on a single scanner's exception.

## Adding a new scanner

1. Create `app/scanners/foo.py` subclassing `BaseScanner`. Implement `scanner_name` and `scan()` returning a list of asset dicts (use `self.create_asset(...)`).
2. Register it in `app/scanners/registry.py` and add `"foo"` to `config.yml`'s `enabled_scanners`.
3. Update the correlator if the new assets should link into applications. The correlator's 11-pass structure makes this incremental — usually one new pass.
4. Add tests in `tests/test_phase2_scanners.py` (shape + project-tagging) and `tests/test_phase5_correlator.py` (linking via synthetic fixtures).

## Resetting the database

```bash
mongosh "$INFRADOCS_MONGO_URI" --eval 'db.getSiblingDB("infradocs").dropDatabase()'
python -m app.agent scan
```
