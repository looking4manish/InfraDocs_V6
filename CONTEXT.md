# InfraDocs — LLM Context

**Read this first.** This is the single onboarding doc for an AI assistant working on this
repo. It gives you the whole mental model in one page, then **breadcrumbs** telling you which
files/docs to open for the specific task you've been given. (For a human "what is this + how
do I deploy it" walkthrough, see [`README.md`](README.md).)

> The repo directory is named `InfraDocs_V6`, but the product is well past single-host "V6".
> It is now a deployable Docker product with auth, a setup wizard, multi-server federation,
> an optional AI layer, and a unified Web tab.

---

## 1. What this is

An **infrastructure documentation cockpit**. It scans one or more servers → correlates →
exposes → visualizes → **acts on** everything running on them.

Pipeline: **scanners → correlator → MongoDB → FastAPI → React frontend.**

The original live instance runs at https://infra.ocialwaysfree.site/ (native deployment).

## 2. ⚠️ Two deployments — never conflate them

1. **Live / legacy — `infra.ocialwaysfree.site`** (the OCI "primary" box):
   native systemd service `infradocs-v6-api.service` runs `uvicorn app.api.main:app` on
   `127.0.0.1:8004` from **this repo**; host nginx serves `frontend/dist/` and proxies
   `/api/` → `:8004`; its own MongoDB. **This is production — keep it up.**
   - **GOTCHA:** nginx serves `frontend/dist/` **live**. A bare `npx vite build` in the repo
     instantly changes production. To test compilation only, build elsewhere:
     `npx vite build --outDir /tmp/ifd-check`.
2. **Product / test — dockerized stack** (`deploy/docker/`): compose of MongoDB + API + Caddy.
   The API container runs host-network + host-PID and mounts the host FS read-only at `/host`
   (so scanners see real containers/processes/ports/configs). Installed by `deploy.sh`,
   removed by `remove.sh`. **This is the future of the project.**

## 3. Capabilities (what exists today)

- **Auth:** bcrypt + DB-backed session tokens (`Authorization: Bearer`). Seeded `admin` user
  with `must_change_password`. `verify_auth` also accepts HTTP Basic (DB user or
  config-cred fallback) and `INFRADOCS_AUTH_DISABLED=1` for local dev.
- **First-run wizard:** server role (standalone/primary/secondary), exposure (domain +
  public-IP detect / Tailscale / Cloudflare Tunnel), optional AI config. Gated on
  `settings.setup_complete`.
- **Ten scanners:** docker, compose, systemd, port, storage, nginx, **caddy**, **cloudflared**,
  **certs**, **cron**. nginx/caddy/cloudflared are pluggable **exposure detectors** (report
  mechanism + public hostname).
- **Correlator:** joins flat assets into per-application docs with `links[]` evidence.
- **AI layer (3 tiers):** recognize (deterministic) → LLM enrich (label unknowns) → fleet
  insights. Any OpenAI-compatible endpoint; disabled cleanly when unset; only non-sensitive
  metadata sent.
- **Web tab:** `/api/endpoints` — every reachable UI/service across the fleet, deduped by
  host/port, with browsable URLs + access scope (internet/localhost/tailnet).
- **Federation:** primary mints join tokens; secondaries push scans **outbound** to the
  primary's `/api/federation/ingest` (NAT-friendly).
- **Actions:** guarded dispatcher (start/stop/restart/logs/enable/disable/…) + audit log;
  `infradocs-v6-*` units self-protected (409).
- **Theme:** "Neon-Depth" (MongoDB-green on dark), static, lens-based navigation.

## 4. Data model — 30 seconds

Every asset lands in **exactly one bucket**: a `~/projects/<name>` project bucket, or the
single `System` bucket. Enforced by `correlator.py`, checked by `audit_ownership()`. Rule:
**only `~/projects/<X>` paths name a project; never infer from a string prefix** (a V5
regression tests guard). Mongo collections (db `infradocs`): `assets`, `applications`,
`ports`, `storage`, `actions_log`, `scan_logs`, `settings` (wizard + AI config), `ai_labels`,
federation join/server records.

## 5. Repo map

```
app/
├── core/      config_loader, db_manager, project_detector, recognize, hostpath, logger
├── scanners/  docker, compose, systemd, port, storage, nginx, caddy, cloudflared, certs, cron
├── correlator.py · actions.py · ai.py · auth.py · federation.py
├── blast_radius.py · teardown.py · ports_registry.py · storage_registry.py
├── agent.py   CLI: python -m app.agent scan
└── api/       main.py · dependencies.py · routers/{auth,setup,federation,endpoints,ai,
                 assets,projects,applications,ports,storage,scans,actions,health}.py
frontend/      React 19 + Vite + Tailwind + React Query (src/App.jsx gate, pages/, components/)
deploy/        docker/ (deploy.sh, remove.sh, compose, Caddyfile, Dockerfiles) · native *.service/*.conf
docs/          ARCHITECTURE · DEPLOY · DEVELOPMENT · V7_PLAN · REGISTRY (root) · phases/
tests/         pytest suite (auth, setup, federation, scanners, correlator, actions, …)
```

---

## 6. 🧭 Breadcrumbs — where to look, by task

| If your task is about… | Open these |
|---|---|
| **Deploying / running it** | [`README.md`](README.md) (quick start) → [`docs/DEPLOY.md`](docs/DEPLOY.md) (docker product + native), `deploy/docker/{deploy.sh,remove.sh,docker-compose.yml}` |
| **Local dev / tests / conventions** | [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md), `tests/` |
| **How it's structured / why** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Auth / login / sessions** | `app/auth.py`, `app/api/dependencies.py` (`verify_auth`), `app/api/routers/auth.py`, `frontend/src/App.jsx` |
| **Setup wizard / first run** | `app/api/routers/setup.py`, `frontend/src/pages/Setup.jsx` |
| **A scanner / new asset type** | `app/scanners/<name>.py`, `app/scanners/registry.py`, `config.yml` (`enabled_scanners`); exposure detectors = nginx/caddy/cloudflared |
| **Correlation / application docs / links** | `app/correlator.py`, `app/core/project_detector.py`; tests `test_v7_phase1_correlator.py` |
| **AI labeling / insights** | `app/ai.py`, `app/core/recognize.py`, `app/api/routers/ai.py`; model notes in §7 |
| **Web tab / endpoints list** | `app/api/routers/endpoints.py`, `frontend/src/pages/LensHome.jsx` (Web lens) |
| **Federation / multi-server** | `app/federation.py`, `app/api/routers/federation.py`; `ServersLens` mock in `LensHome.jsx` |
| **Actions / card+action registry** | `app/actions.py`, [`REGISTRY_SPEC.md`](REGISTRY_SPEC.md), `frontend/src/registry/cards.js`, `components/ActionBar.jsx` |
| **Reading host configs in a container** | `app/core/hostpath.py` (the `/host` mount) — never read `/etc/...` directly |
| **Teardown / blast radius** | `app/teardown.py`, `app/blast_radius.py` |
| **The roadmap / what's next** | [`docs/V7_PLAN.md`](docs/V7_PLAN.md) (§0 reality update), and §8 below |
| **History of a past session** | `git log` — the per-session `*HANDOFF*.md` files and `docs/phases/PHASE_*_STATUS.md` build journal were pruned once their work landed on `main` |

---

## 7. Run / develop (cheat sheet)

```bash
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env                                  # set INFRADOCS_MONGO_URI
python -m app.agent scan --summary                    # scan + populate
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8005   # API (≠ prod 8004)
cd frontend && npm install && npm run dev             # → :5173 (proxies /api → :8004)
python -m pytest tests/ -v                            # tests
sudo systemctl restart infradocs-v6-api.service       # restart live API after a code change
npx vite build --outDir /tmp/ifd-check                # compile-check WITHOUT clobbering live dist
```

**AI model findings** (against the user's Ollama at `https://ai.ocialwaysfree.site/v1`):
- ✅ `gpt-oss:120b-cloud` (~8s) and `qwen3-coder:480b-cloud` (~4s) — fast, clean JSON.
  **Recommended default = `gpt-oss:120b-cloud`.**
- ❌ `ministral-3:8b` too weak (ignores schema); `kimi-k2.6:cloud` /
  `mistral-large-3:675b-cloud` time out (>150s).
- Two fixes that made it work: strip ```` ```json ```` fences, and send a real `User-Agent`
  (the gateway 403s the default `python-urllib` UA).

## 8. Open items / next

- **Command dispatch** (federation primary → secondary actions) — requested, not started.
- **Federation viewing UI** — `/api/federation/servers` exists; wire up `ServersLens` in
  `LensHome.jsx` + "Add a server" (mint token) + a server switcher.
- **Production cutover** — archive native OCI → fresh dockerized primary → onboard OCI-P +
  N150 as secondaries. User configures exposure himself; keep the product **generic**.
- **Scanner wave 1 remainder** (per V7_PLAN): `db.py`, firewall exposure cross-check,
  `backup.py`, substrate IMDS/SDK, `hardware.py` (N150).
- N150 testing (user runs it; sites there exposed via Cloudflare tunnel).

## 9. Key reference

| Item | Value |
|---|---|
| Hosts in scope | OCI (primary), OCI-P, N150 |
| SSH | `biwi` = OCI-P (`msinha@100.70.18.9`, key `~/.ssh/master_key`) |
| Default login | `admin / Changeme001` (forced change); config-cred Basic fallback `admin:Changeme001` |
| Ollama | `https://ai.ocialwaysfree.site/v1`, model `gpt-oss:120b-cloud` |
| Live native deploy | `infradocs-v6-api.service` :8004 + host nginx `infra.ocialwaysfree.site` |
| Docker API/web ports | API `:8090`, Caddy web `:8081` (host network) |
| Branch | `feature/neon-depth-theme` (kept in sync with `origin/main`) |
| Commit footer | `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` |
