# InfraDocs — Project Context (for fresh Claude sessions)

The single-page brief a new session should read to be productive without re-deriving
everything. Deep details live in `docs/`; the latest deep handoff is
[`CONTEXT_FOR_LLM.md`](CONTEXT_FOR_LLM.md).

> The repo is named `InfraDocs_V6` but the product is well past single-host V6. It is now a
> deployable Docker product with auth, a setup wizard, federation, an AI layer, and a Web tab.

---

## What this is

An **infrastructure documentation cockpit**. It scans one or more servers → correlates →
exposes → visualizes → **acts on** everything running on them. The original live instance
runs at https://infra.ocialwaysfree.site/ (native deployment — see "Two deployments").

Pipeline: **scanners → correlator → MongoDB → FastAPI → React frontend.**

## ⚠️ Two deployments — don't conflate them

1. **Live / legacy — `infra.ocialwaysfree.site`** (this machine, "OCI primary"):
   native systemd service `infradocs-v6-api.service` running `uvicorn app.api.main:app` on
   `127.0.0.1:8004`, from **this repo**; host nginx serves `frontend/dist/` + proxies
   `/api/` → `:8004`; separate MongoDB. **Production — keep it up.** Because nginx serves
   `frontend/dist/` live, **never** run a bare `vite build` here — use `--outDir /tmp/...`.
2. **Product / test — dockerized stack** (`deploy/docker/`): compose of MongoDB + API
   (host net + host PID, host FS mounted read-only at `/host`) + Caddy web. Installed via
   `deploy.sh`, removed via `remove.sh`. This is the future of the project.

## Where things live

```
/home/msinha/projects/InfraDocs_V6/
├── app/
│   ├── core/             config_loader, db_manager, project_detector, recognize, hostpath, logger
│   ├── scanners/         docker, compose, systemd, port, storage, nginx, caddy,
│   │                       cloudflared, certs, cron  (+ base, registry)
│   ├── correlator.py     flat assets → application docs (+ links[] evidence)
│   ├── actions.py        action dispatcher + allow-list
│   ├── ai.py             optional LLM layer: label_service + fleet_insights
│   ├── auth.py           bcrypt + DB session tokens
│   ├── federation.py     primary mint-token / secondary outbound ingest
│   ├── blast_radius.py, teardown.py    guarded project teardown
│   ├── ports_registry.py, storage_registry.py
│   ├── agent.py          CLI: python -m app.agent scan
│   └── api/
│       ├── main.py       FastAPI app, lifespan (seeds admin), router includes
│       ├── dependencies.py   verify_auth (Bearer | Basic | disabled), get_db
│       └── routers/      auth, setup, federation, endpoints, ai, assets, projects,
│                           applications, ports, storage, scans, actions, health
├── frontend/             React 19 + Vite + Tailwind + React Query (Neon-Depth theme)
├── deploy/
│   ├── docker/           deploy.sh, remove.sh, docker-compose.yml, Caddyfile, Dockerfile(.web)
│   └── *.service/*.conf/install_*.sh   legacy native systemd + nginx
├── docs/                 ARCHITECTURE, DEPLOY, DEVELOPMENT, V7_PLAN, phases/
├── CONTEXT.md            this file
└── CONTEXT_FOR_LLM.md    latest deep handoff
```

## Auth (replaced the old HTTP-Basic-only model)

bcrypt password hashing + **DB-backed session tokens** sent as `Authorization: Bearer`.
A default `admin` user is seeded with `must_change_password` (default `admin / Changeme001`).
`app/api/dependencies.py::verify_auth` accepts: a valid Bearer session, OR HTTP Basic
(DB user bcrypt **or** config-credential fallback), OR `INFRADOCS_AUTH_DISABLED=1`.
Routers: `app/api/routers/auth.py` (`/login` throttled, `/change-password`, `/logout`,
`/me`). Frontend gate: `frontend/src/App.jsx` (loading → login → change-password → setup →
ready); token in `localStorage` as `ifd_token`; a 401 fires `ifd-unauthorized`.

## First-run wizard

`frontend/src/pages/Setup.jsx` → `app/api/routers/setup.py`. Captures server name, role
(standalone / primary / secondary), exposure (domain + public-IP detection / Tailscale /
Cloudflare Tunnel), and **optional AI config** (endpoint / key / model). Gated on
`settings.setup_complete`. `/detect-ip` classifies every interface and loudly flags
Tailscale/VPN/CGNAT/private addresses so a user never points DNS at an unreachable IP.

## Federation (multi-server)

Primary mints join tokens (`POST /api/federation/tokens`); secondaries push scan data
**outbound** to the primary's `POST /api/federation/ingest` (NAT-friendly).
`GET /api/federation/servers` lists known servers. Command dispatch (primary→secondary
actions) is **designed, not yet built**.

## AI layer (3 tiers — built & verified)

1. **Recognize** (`app/core/recognize.py`) — deterministic port/image/process → label.
2. **Enrich** (`app/ai.py::label_service`, `POST /api/ai/enrich`) — LLM labels unknowns,
   cached in the `ai_labels` collection.
3. **Insights** (`app/ai.py::fleet_insights`, `/api/ai/insights`) — one LLM call over the
   whole inventory → summary + observations + recommendations.

Any OpenAI-compatible `/chat/completions` endpoint (OpenAI / Ollama / vLLM). Disabled
cleanly when unset; only non-sensitive metadata is sent; the key is a stored secret.
Recommended model against the user's Ollama: **`gpt-oss:120b-cloud`** (clean JSON, ~8s).
Two fixes that made it work: strip ```` ```json ```` fences, and send a real `User-Agent`
(the gateway 403s the default `python-urllib` UA).

## Web tab

`GET /api/endpoints` (`app/api/routers/endpoints.py`) aggregates exposure blocks + listening
ports into every reachable UI/service across the fleet — deduped by host/port, with
browsable URLs and an access scope (internet / localhost / tailnet). Rendered as the **Web**
lens in `frontend/src/pages/LensHome.jsx`.

## Data model — the 30-second version

Every asset lands in **exactly one bucket**: a `~/projects/<name>` project bucket, or the
single `System` bucket. Enforced by `correlator.py`, checked by `audit_ownership()`. Project
attribution rule: **only `~/projects/<X>` paths name a project; never infer from a string
prefix** (a V5 regression that tests guard). The correlator persists `links[]` evidence per
join so the UI renders topology instead of re-deriving it.

Mongo collections (db `infradocs`): `assets`, `applications`, `ports`, `storage`,
`actions_log`, `scan_logs`, `settings` (wizard + AI config), `ai_labels`, federation
join/server records.

## Action dispatcher allow-list

`docker_container` (start/stop/restart/logs/…), `docker_compose` (up/down/restart/…),
`systemd_service` (start/stop/restart/status/logs/enable/disable), `systemd_timer`,
`nginx_server_block` (test/reload), plus Wave-B additions (image pull/prune, port
identify/kill, etc. — see `REGISTRY_SPEC.md`). Self-protection: any `infradocs-v6-*` unit →
409. Every attempt (success/failed/refused) is audited.

## Conventions

- **Add a scanner:** subclass `BaseScanner`, emit via `self.create_asset(..., project=…)`,
  register in `app/scanners/registry.py`, add to `enabled_scanners` in `config.yml`. Every
  asset gets a project (folder name or `"System"`).
- **Add an API endpoint:** new file in `app/api/routers/`, include in `app/api/main.py`,
  depend on `verify_auth` unless intentionally public.
- **Read host configs from inside the container** via `app/core/hostpath.py` (the `/host`
  mount) — don't read `/etc/...` directly when containerized.
- **Commits:** small, per sub-task; co-author footer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Run / develop

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env                                  # set INFRADOCS_MONGO_URI
python -m app.agent scan --summary                    # scan + populate
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8005   # API (≠ prod 8004)
cd frontend && npm install && npm run dev             # → :5173 (proxies /api → :8004)
python -m pytest tests/ -v                            # tests
sudo systemctl restart infradocs-v6-api.service       # restart live API after code change
# Build frontend for prod WITHOUT clobbering live dist:  npx vite build --outDir /tmp/ifd-check
```

## Key reference

| Item | Value |
|---|---|
| Hosts in scope | OCI (primary), OCI-P, N150 |
| SSH | `biwi` = OCI-P (`msinha@100.70.18.9`, key `~/.ssh/master_key`) |
| Default login | `admin / Changeme001` (forced change); config-cred Basic fallback `admin:Changeme001` |
| Ollama | `https://ai.ocialwaysfree.site/v1`, model `gpt-oss:120b-cloud` |
| Live native deploy | `infradocs-v6-api.service` :8004 + host nginx `infra.ocialwaysfree.site` |
| Branch | `feature/neon-depth-theme` (in sync with `origin/main`) |

## Known open items / next

- **Command dispatch** (federation primary→secondary actions) — requested, not started.
- **Federation viewing UI** — `/api/federation/servers` exists; `ServersLens` in
  `LensHome.jsx` is still a mock → wire it up + "Add a server" (mint token) + server switcher.
- **Production cutover** — archive native OCI → fresh dockerized primary → onboard OCI-P +
  N150 as secondaries (user configures exposure himself; keep the product generic).
- N150 testing (user runs it; sites there exposed via Cloudflare tunnel).
