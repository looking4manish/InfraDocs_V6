# InfraDocs

**An infrastructure documentation cockpit — and now a deployable, multi-server, AI-enhanced product.**

InfraDocs scans one or more servers, correlates everything it finds (containers, compose
files, systemd units, listening ports, nginx/Caddy/Cloudflare-tunnel exposures, storage,
certs, cron) into per-application documents, and renders a React cockpit that answers
"what is running on my fleet, where is it exposed, and what is it?" — without manually
re-joining `docker ps`, `systemctl status`, `nginx -T`, `ss`, and `du`.

> The repo directory is still named `InfraDocs_V6`, but the product has moved well past
> the original single-host "V6". It now ships as a Docker product with a first-run setup
> wizard, bcrypt auth, primary/secondary federation, an optional AI labeling layer, and a
> unified Web tab. If you're an AI assistant picking this up, start at
> [`CONTEXT.md`](CONTEXT.md) (full mental model + task breadcrumbs); for the roadmap see
> [`docs/V7_PLAN.md`](docs/V7_PLAN.md).

## What it does

- **Discovers** infrastructure via ten scanners: docker, compose, systemd, listening
  ports, storage, nginx, **Caddy**, **Cloudflare tunnel (cloudflared)**, **certs**, and
  **cron** — exposure detectors are pluggable per category.
- **Correlates** the flat scan output into per-application documents with `links[]`
  evidence (the heart of the app — see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)).
- **Exposes** the data through FastAPI (`/api/applications`, `/api/assets`,
  `/api/projects`, `/api/ports`, `/api/storage`, `/api/endpoints`, `/api/scans`,
  `/api/actions`, plus `/api/auth`, `/api/setup`, `/api/federation`, `/api/ai`).
- **Labels** unknown services with an optional **AI layer** (deterministic recognition →
  LLM enrichment → fleet insights) against any OpenAI-compatible endpoint.
- **Surfaces** every reachable UI/service across the fleet in one **Web tab** — clickable
  URL, which server, which service, access scope (internet / localhost / tailnet).
- **Acts on** containers / systemd units / nginx via `POST /api/assets/{id}/action` and
  `POST /api/applications/{name}/action`, with a full audit log at `/api/actions/`.
- **Visualizes** it through a React + Vite SPA in the "Neon-Depth" theme (MongoDB-green):
  lens-based home (Dashboard / Projects / Servers / Web / Resources / Assets), application
  topology lanes, registries, and an audit log.

## Two ways to run it

### 1. Docker product (recommended — the deployable path)

The packaged product is a docker-compose stack (MongoDB + API + Caddy web) driven by an
interactive installer that ends at a browser-reachable setup wizard.

```bash
git clone https://github.com/looking4manish/InfraDocs_V6.git
cd InfraDocs_V6/deploy/docker
./deploy.sh          # interactive: builds, starts the stack, prints the wizard URL
# …open the printed URL, log in (admin / Changeme001), change the password, run the wizard
./remove.sh          # clean teardown
```

The API container runs with host network + host PID and mounts the host filesystem
read-only at `/host`, so the scanners see real containers, processes, ports, and configs.
You configure exposure (domain + DNS, Tailscale, or Cloudflare Tunnel) in the wizard — the
product is **generic**, nothing host-specific is hardcoded. See
[`docs/DEPLOY.md`](docs/DEPLOY.md).

### 2. Local dev (native)

Requirements: Python 3.12, Node 20+, MongoDB.

```bash
git clone https://github.com/looking4manish/InfraDocs_V6.git
cd InfraDocs_V6

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set INFRADOCS_MONGO_URI

python -m app.agent scan --summary                       # one-shot scan
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8004   # API

cd frontend && npm install && npm run dev                # → http://localhost:5173
```

First run opens a **login screen** (seeded `admin` / `Changeme001`, forced password
change) then the **setup wizard**. See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

> ⚠️ **Never run a bare `npx vite build` in this repo.** The live site
> (`infra.ocialwaysfree.site`) serves `frontend/dist/` directly via nginx, so a bare build
> instantly changes production. Always build to a throwaway dir:
> `npx vite build --outDir /tmp/ifd-check`.

## Auth

bcrypt password hashing + DB-backed session tokens (sent as `Authorization: Bearer`).
A default `admin` user is seeded with `must_change_password`. A config-credential HTTP
Basic path remains as a fallback, and `INFRADOCS_AUTH_DISABLED=1` bypasses auth for local
dev. See `app/auth.py` and `app/api/routers/auth.py`.

## Federation (multi-server)

One **primary** mints join tokens; each **secondary** pushes its scan data **outbound** to
the primary's `/api/federation/ingest` (NAT-friendly — a secondary never needs an inbound
port). Endpoints: `POST /api/federation/tokens`, `GET /api/federation/servers`,
`POST /api/federation/ingest`. Command dispatch (primary → secondary actions) is designed
but not yet built.

## Testing

```bash
python -m pytest tests/ -v
```

Suites cover scanner contracts, correlation, ports/storage registries, the ownership
audit, the action dispatcher, auth, setup wizard, federation, exposure detectors, cert/cron
scanners, teardown/blast-radius, and FastAPI endpoints with a real MongoDB. Integration
tests skip automatically when `INFRADOCS_MONGO_URI` is unset.

## Project layout

```
.
├── app/
│   ├── core/             # config, db_manager, project_detector, recognize, hostpath, logger
│   ├── scanners/         # docker, compose, systemd, port, storage, nginx, caddy,
│   │                     #   cloudflared, certs, cron (+ base, registry)
│   ├── correlator.py     # joins flat assets into application docs (+ links[] evidence)
│   ├── actions.py        # action dispatcher + allow-list
│   ├── ai.py             # optional LLM layer (label_service + fleet_insights)
│   ├── auth.py           # bcrypt + DB sessions
│   ├── federation.py     # primary/secondary join + ingest
│   ├── blast_radius.py / teardown.py        # guarded project teardown
│   ├── agent.py          # CLI: python -m app.agent scan
│   └── api/              # FastAPI app + routers (auth, setup, federation, endpoints, ai, …)
├── frontend/             # React 19 + Vite + Tailwind + React Query (Neon-Depth theme)
├── deploy/
│   ├── docker/           # docker-compose product: deploy.sh, remove.sh, Caddyfile, Dockerfiles
│   └── *.service / *.conf / install_*.sh    # legacy native systemd + nginx
├── docs/                 # ARCHITECTURE, DEPLOY, DEVELOPMENT, V7_PLAN, phases/
├── tests/                # pytest suite (unit + integration)
├── CONTEXT.md            # single LLM-onboarding doc (mental model + task breadcrumbs)
├── config.yml            # non-secret app config
└── .env.example          # copy to .env; never commit .env
```

## Status

The original V6 build phases (1–9A: foundation → scanners → API → frontend → correlation →
nginx exposure → registries → operational controls) are all complete. The product has since
gained: bcrypt/session auth, a first-run wizard, the Docker product (`deploy.sh`/`remove.sh`),
multi-mechanism exposure detection (nginx/Caddy/cloudflared), primary/secondary federation,
the AI labeling layer, and the unified Web tab.

**In flight / next:** command dispatch (primary→secondary actions), the full federation
viewing UI (Servers page + token mint + server switcher), and the production cutover
(fresh dockerized primary on OCI, OCI-P + N150 as secondaries). See
[`docs/V7_PLAN.md`](docs/V7_PLAN.md) and [`CONTEXT.md`](CONTEXT.md).

## License

Personal project. No formal license declared yet.
