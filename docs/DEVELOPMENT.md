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
#   INFRADOCS_API_PASSWORD=                          # leave empty in dev, falls back to dev_password

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

The agent runs all six scanners, writes raw assets, then runs the correlator and writes applications. `--summary` prints by-category and by-project counts at the end.

### Start the API

```bash
source venv/bin/activate
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8004
```

Hit `http://localhost:8004/docs` for the auto-generated OpenAPI UI. Auth: HTTP Basic, dev creds `msinha:msinha123` (set `INFRADOCS_API_PASSWORD` in `.env` to override).

### Start the frontend dev server

```bash
cd frontend
npm run dev
# → http://localhost:5173/
```

Vite proxies `/api/*` to `http://127.0.0.1:8004`, so the API must already be running. Hot module reload is on.

### Trigger a scan from the running API

```bash
curl -u msinha:msinha123 -X POST http://localhost:8004/api/scans/trigger
# returns {"scan_id":"...","status":"queued"}; scan runs as a BackgroundTask
```

Or click "Run scan" in the UI header — same effect.

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Tests are split into four files:

- `test_phase1.py` — core utilities, config loader, project detector, DB connection
- `test_phase2_scanners.py` — scanner integration tests against the local host
- `test_phase3_api.py` — FastAPI endpoints with dependency overrides (uses a throwaway test DB)
- `test_phase5_correlator.py` — correlator unit tests + one real-OCI integration test

Tests that require MongoDB are auto-skipped if `INFRADOCS_MONGO_URI` is unset. So `pytest tests/` is safe even without Mongo configured.

Run a single file: `pytest tests/test_phase5_correlator.py -v`.

## Project layout (developer view)

```
app/
├── agent.py              # CLI entry — `python -m app.agent scan`
├── correlator.py         # raw assets → application documents (11 passes)
├── core/
│   ├── config_loader.py  # Pydantic models + load_dotenv
│   ├── db_manager.py     # MongoDB wrapper, single DB
│   ├── logger.py         # JSON structured logger
│   └── project_detector.py
├── scanners/
│   ├── base.py           # BaseScanner ABC
│   ├── systemd.py        # systemctl-driven
│   ├── docker.py         # docker SDK
│   ├── compose.py        # walks projects_root
│   ├── nginx.py          # parses /etc/nginx/sites-enabled (brace-aware)
│   ├── port.py           # ss -tulpnH + /proc/<pid>/cwd
│   ├── storage.py        # df
│   └── registry.py       # name → class map
└── api/
    ├── main.py           # FastAPI app, lifespan, CORS
    ├── dependencies.py   # get_config, get_db, verify_auth
    └── routers/
        ├── health.py
        ├── assets.py
        ├── applications.py
        ├── projects.py
        └── scans.py
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
