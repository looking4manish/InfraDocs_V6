# InfraDocs V6

**A single dashboard that aggregates everything about every application running on a host.**

For each app, V6 stitches together its docker container(s), compose file, nginx server block(s), exposed URLs, port mappings, on-disk storage paths and sizes, environment-variable keys, and systemd unit(s) into one document — so you can answer "what does this app consist of?" or "what do I need to clean up to remove it?" in one place, without manually correlating across `docker ps`, `systemctl status`, `nginx -T`, and `du`.

V6 is the rewrite of an earlier V5 that distributed scanning across multiple hosts and turned into a debugging mess. V6 deliberately targets one host (production-quality OCI-only) before reintroducing multi-host support.

## What it does

- **Discovers** infrastructure via six scanners: systemd (services + timers), docker (containers, images, volumes, networks), docker-compose files, nginx server blocks, listening network ports, and storage mounts.
- **Correlates** the flat scan output into per-application documents (the heart of V6 — see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)).
- **Exposes** the data through a FastAPI service (`/api/applications`, `/api/assets`, `/api/projects`, `/api/ports`, `/api/storage`, `/api/scans`, `/api/actions`).
- **Acts on** containers / systemd units / nginx via `POST /api/assets/{id}/action` and `POST /api/applications/{name}/action` (start/stop/restart/logs/...), with a full audit log at `/api/actions/`.
- **Visualizes** it through a React+Vite SPA: Dashboard, Applications (list + rich detail), Projects, Ports registry (+ live probe), Storage (+ owner breakdown), Actions audit log, and a flat Asset browser.

## Quick start (local dev)

Requirements: Python 3.12, Node 20+, MongoDB (any modern version; replica set works too).

```bash
# 1. Clone and enter the repo
git clone <your-fork>
cd InfraDocs_V6

# 2. Python backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure MongoDB
cp .env.example .env
# Edit .env and set INFRADOCS_MONGO_URI to your Mongo connection string.
# For a local Mongo with no auth: mongodb://localhost:27017/

# 4. Discover infrastructure (one-shot scan)
python -m app.agent scan --summary

# 5. Start the API
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8004
# In another shell:

# 6. Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173/  (proxies /api/* to :8004)
```

Default API credentials in dev: `msinha` / `msinha123` (set `INFRADOCS_API_PASSWORD` in `.env` to override). See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for more workflows.

## Optional: production deploy with nginx + systemd

For a real "expose to internet via nginx" deploy (Ubuntu/Debian), the scripts in [`deploy/`](deploy/) install a systemd unit for the API and an nginx vhost that static-serves the built frontend. Both are OCI-specific in the example but easy to adapt — read [`docs/DEPLOY.md`](docs/DEPLOY.md) before running.

## Testing

```bash
python -m pytest tests/ -v
```

The suite is 118 tests covering scanner contracts, application correlation logic, ports/storage registries, the ownership audit, the action dispatcher (with mocked subprocess/docker), and FastAPI endpoints with a real MongoDB. Integration tests are skipped automatically if `INFRADOCS_MONGO_URI` is not set.

## Project layout

```
.
├── app/
│   ├── core/             # config, logger, db_manager, project_detector
│   ├── scanners/         # one module per scanner + a registry
│   ├── correlator.py     # joins flat assets into application documents
│   ├── agent.py          # CLI entry: `python -m app.agent scan`
│   └── api/              # FastAPI app + routers
├── frontend/             # React 19 + Vite 8 + Tailwind 3 + React Query
├── deploy/               # systemd unit, nginx vhost, install/uninstall scripts
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── DEPLOY.md
│   └── phases/           # per-phase build history
├── tests/                # pytest suite (unit + integration)
├── config.yml            # non-secret app config
├── .env.example          # copy to .env; never commit .env
└── requirements.txt
```

## Status

| Phase | Status |
|---|---|
| 1 Foundation | ✅ |
| 2 Scanners | ✅ |
| 3 API | ✅ |
| 4 Frontend | ✅ (awaiting UI polish round) |
| 5 Scanner enrichment + Application correlation | ✅ |
| 6 Nginx exposure | ✅ |
| 7 Project/System linkage + Ports registry + Storage registry | ✅ |
| 8 Operational controls | ✅ |
| 9A Frontend extension (apps/ports/storage/actions UI) | ✅ |
| 9B UI polish + frontend tests + hardening | pending |

See [`docs/phases/`](docs/phases/) for the build journal — each phase has a status doc covering scope, decisions, bugs caught, and what landed.

## License

Personal project. No formal license declared yet.
