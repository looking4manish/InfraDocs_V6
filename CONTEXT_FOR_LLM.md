# InfraDocs — Project Context (handoff for another LLM session)

**Generated:** 2026-06-27 · **Repo:** `/home/msinha/projects/InfraDocs_V6` · **Owner:** Manish Sinha

> Read this top-to-bottom before answering anything about InfraDocs. The single most
> common confusion is mistaking the **live native deployment** for the **dockerized
> product** — they are different things running different code. See §3.

---

## 1. What InfraDocs is

An **infrastructure documentation cockpit**. It scans one or more servers, correlates
what it finds (containers, processes, listening ports, nginx/caddy/cloudflared
exposures, storage, certs, cron), and renders a React UI that answers "what is running
on my fleet, where is it exposed, and what is it?"

**Pipeline:** scanners → correlator → MongoDB → FastAPI → React frontend.

**Roadmap (V7):** turn it into a deployable *product* (docker-compose, first-run
wizard), then **multi-server federation** (one primary, many secondaries) with
**command dispatch** (primary triggers actions on secondaries).

---

## 2. Architecture

| Layer | What | Where |
|---|---|---|
| Scanners | docker, processes, network_port, nginx, caddy, cloudflared, storage, certs, cron | `app/scanners/` |
| Correlator | merges scanner output into assets/projects/applications | `app/correlate*` |
| API | FastAPI; routers: auth, setup, federation, endpoints, ai, assets, projects, applications, ports, storage, scans, actions | `app/api/` |
| DB | MongoDB | native: separate mongo · docker: `infradocs-mongo` |
| Frontend | React + Vite, "Neon-Depth" theme (MongoDB-green), lens-based nav | `frontend/src/` |

**Auth:** bcrypt + DB session tokens (Bearer). Seeded admin `admin / Changeme001` with
`must_change_password`. Config-credential Basic auth is a fallback. Disable with
`INFRADOCS_AUTH_DISABLED`.

**First-run wizard** (`frontend/src/pages/Setup.jsx` → `app/api/routers/setup.py`):
server name, role (standalone/primary/secondary), exposure (domain/tailscale/cloudflare
with public-IP detection), and **optional AI labeling** (endpoint/key/model). Gated on
`settings.setup_complete`.

**Federation (designed, partially built):** primary mints join tokens; secondaries push
**outbound** to `/api/federation/ingest` (NAT-friendly — secondary never needs an inbound
port). Command dispatch (primary→secondary actions) is **not yet built**.

---

## 3. ⚠️ The two deployments — DO NOT CONFUSE THEM

### 3a. LIVE / legacy — `infra.ocialwaysfree.site` (this machine, "OCI primary")
- **Service:** `infradocs-v6-api.service` (systemd, user `msinha`).
- **Code:** THIS repo — `/home/msinha/projects/InfraDocs_V6` (current `main`).
- **Run:** `venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8004`.
- **nginx** `infra.ocialwaysfree.site`: serves `frontend/dist` (static) + proxies
  `/api/` → `127.0.0.1:8004`. TLS on 443.
- This is **native, not docker**. It is the production site and must stay up.
- **GOTCHA:** nginx serves `frontend/dist` **live**. Running a bare `npx vite build` in
  the repo overwrites that dist and instantly changes the live site. ALWAYS build to a
  throwaway dir: `npx vite build --outDir /tmp/ifd-check`. (This bit us once.)

### 3b. PRODUCT / test — dockerized stack (was on OCI-P, **now stopped**)
- docker-compose at `deploy/docker/docker-compose.yml`: `mongo` + `api`
  (host network + host pid, reads host configs via `/host` mount) + `web` (Caddy).
- Was running on OCI-P for testing. **As of 2026-06-27 it is brought DOWN**
  (`docker compose down` — containers + network removed, ports 8090/8081 closed).
- This is the future of the project (the deployable product); the native one is legacy.

**Cutover plan (not yet executed):** archive the native OCI folder + nginx config →
fresh dockerized install on OCI as **primary** → onboard OCI-P and N150 as
**secondaries**. The product must stay **generic**: the user configures exposure
(Cloudflare/nginx/DNS A-record) himself at install time — do **not** hardcode anything
OCI-specific.

---

## 4. The AI layer (3 tiers) — built & verified working

Goal: identify services the deterministic rules can't, and produce fleet-level insight.

- **Tier 1 — deterministic recognition** (`app/core/recognize.py`): port/image/process
  → label. Knows MongoDB, Prometheus, Postgres, Qdrant, Grafana, etc.
- **Tier 2 — LLM enrichment** (`app/ai.py` `label_service`, router `app/api/routers/ai.py`
  `/enrich`): sends non-sensitive evidence for *unknown* services to an OpenAI-compatible
  endpoint, caches results in `ai_labels` collection.
- **Tier 3 — fleet insights** (`app/ai.py` `fleet_insights`, `/insights`): one LLM call
  over the whole inventory → summary + observations + recommendations, stored in settings.

**LLM client** (`app/ai.py`): any OpenAI-compatible `/chat/completions` (OpenAI, local
Ollama, vLLM). Disabled cleanly when unset. Only non-sensitive metadata is sent. Key is
a secret (stored in settings, never logged).

**Two bugs that blocked it (both fixed):**
1. Small models wrap JSON in ```` ```json ```` fences → `_parse_json` strips fences.
2. **HTTP 403** — the gateway in front of the user's Ollama blocks the default
   `python-urllib` User-Agent. Fixed by sending `User-Agent: InfraDocs/1.0`. *This was
   the real blocker.*

**Model findings** (against user's Ollama at `https://ai.ocialwaysfree.site/v1`):
- ✅ `gpt-oss:120b-cloud` (~8s) and `qwen3-coder:480b-cloud` (~4s) — fast, clean JSON. **Recommended default = `gpt-oss:120b-cloud`.**
- ❌ `ministral-3:8b` — too weak (ignores schema).
- ❌ `kimi-k2.6:cloud`, `mistral-large-3:675b-cloud` — time out (>150s), impractical.

**Verified live** on OCI-P: Tier 2 labeled the unknown containers; Tier 3 produced real
insight ("Two projects internet-exposed via nginx (discovery.mdbdemo.in:8182,
mhx.mdbdemo.in:8000); many ports open with unknown processes" + recommendations).

---

## 5. Git state (as of 2026-06-27)

- **Branch:** `feature/neon-depth-theme`, **fully in sync with `origin/main`** (0 ahead / 0 behind).
- **Latest commit on `main`:** `9b646c1 fix(ai): send a User-Agent header (gateway 403'd default python-urllib UA)`.
- All feature code/builds are committed and pushed.

Recent commits:
```
9b646c1 fix(ai): send a User-Agent header (gateway 403'd default python-urllib UA)
6b7cbfe fix(ai): robust JSON parsing (strip markdown fences) + stricter minified-JSON prompts
8ee7cde feat(ai): 3-tier service labeling — recognize + LLM enrich + fleet insights
0945fa2 fix(web): dedup endpoints by host/port + browsable URLs (no double port)
352f9d5 feat(web): unified Web tab — every reachable UI/service across the fleet
5d909d0 fix(projects): attribute paths to a project by matching dir-name component
d865299 fix(ui): accurate topology message for systemd-only services
ce36982 feat(ui): neon-depth on the dashboard charts (donut rings + bars)
```

**Uncommitted = non-build junk only** (safe to ignore or clean): a `V7_PHASE35_HANDOFF.md`
edit, a stray `Handoff 2026 06 12 motion.md`, four `frontend/src/**.bak.split|.bak.act`
source backups, and 20 stale `frontend/dist.bak.*` deletions. **No source/build is uncommitted.**

---

## 6. What's done vs pending

**Done & on `main`:**
- Auth (bcrypt + DB sessions), first-run wizard, public-IP detection.
- Dockerized product (compose, `deploy.sh`, `remove.sh`), host-config access via `/host`.
- Exposure detectors (nginx + root-dir attribution, caddy, cloudflared).
- **Web tab** — every reachable UI/service across the fleet, dedup'd, browsable URLs.
- **AI layer (Tier 1+2+3)** — recognize + enrich + insights, verified live.
- Path→project attribution fix (dir-name component match — fixed mxh/mhx not linking).
- Neon-depth charts (3D donut/bars).

**Pending (next work):**
1. **Command dispatch** (federation): primary enqueues actions → secondary polls
   outbound → executes locally → reports back. *Explicitly requested, not started.*
2. **Federation viewing UI:** a real "Servers" page (currently a hardcoded mock in
   `LensHome.jsx` ServersLens) → `/api/federation/servers`; "Add a server" (mint token);
   server switcher to filter views by server.
3. **The cutover** (§3): archive native OCI → fresh docker primary → onboard OCI-P + N150.
4. **N150 testing** (user runs it; websites there are exposed via Cloudflare tunnel).

---

## 7. Operational facts & gotchas (preserve these)

- **Never** run a bare `vite build` in the repo — it overwrites the live `frontend/dist`
  that nginx serves. Use `--outDir /tmp/...`.
- `infra.ocialwaysfree.site` (native systemd `:8004` + host nginx + separate mongo) must
  stay untouched.
- **OCI firewall** drops docker-bridge → host traffic, so in docker the `web` (Caddy)
  container runs on `network_mode: host` and reaches the API at `localhost:<port>`.
- Product must be **generic** — no OCI-specific hardcoding; user configures exposure at install.
- **SSH:** `biwi` = OCI-P (`msinha@100.70.18.9`, key `~/.ssh/master_key`). Servers in scope:
  OCI, OCI-P, N150.
- Config-credential Basic auth = `admin:Changeme001`.
- Only non-sensitive service metadata is ever sent to the LLM; the AI key is a stored secret.
- Ollama endpoint: `https://ai.ocialwaysfree.site/v1`; recommended model `gpt-oss:120b-cloud`.

---

## 8. Key files map

```
app/ai.py                          LLM client + label_service + fleet_insights (UA + fence fixes)
app/core/recognize.py              Tier-1 deterministic service recognition
app/api/routers/ai.py              /status /labels /enrich /insights
app/api/routers/endpoints.py       /api/endpoints — Web tab aggregation (dedup, browsable)
app/api/routers/setup.py           wizard: /status /detect-ip /complete (saves AI config)
app/api/routers/auth.py            /login /change-password /logout /me
app/auth.py                        bcrypt + DB sessions
app/api/dependencies.py            verify_auth (Bearer | Basic | disabled)
app/core/hostpath.py               read host configs through /host mount (container)
app/core/project_detector.py       multi-root project discovery + path→project attribution
app/scanners/{nginx,caddy,cloudflared}.py   exposure detectors
frontend/src/pages/Setup.jsx       wizard UI (incl. AI labeling section)
frontend/src/pages/LensHome.jsx    lens nav incl. Web tab + AI controls (+ mock ServersLens)
frontend/src/api/client.js         axios + Bearer + endpoint map
deploy/docker/docker-compose.yml   mongo + api(host net/pid) + web(Caddy, host net)
deploy/docker/{deploy.sh,remove.sh}  installer + teardown
```
