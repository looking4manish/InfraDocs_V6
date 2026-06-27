# Overnight build — A (Docker product) + B (multi-mechanism exposure)

> 🗄️ **HISTORICAL (as of 2026-06-27).** Progress tracker from the 2026-06-24 overnight run,
> kept for the journal. Both deliverables (Docker product + multi-mechanism exposure) shipped
> and are on `main`. For current state read [`CONTEXT.md`](CONTEXT.md).

> Started 2026-06-24 night. Branch `feature/neon-depth-theme`. Running in Cockpit
> (no tmux) so the session may drop — every step is committed + pushed; this file is
> the live progress tracker. If resuming: read this top-to-bottom, then `git log`.

## Operator's directives (this run)
- ✅ Approved: container gets **read-only access to the whole host disk** (for real storage numbers).
- Deliver **both** by morning:
  - **A** — finish packaging InfraDocs as a deployable **Docker product** + deploy it (parallel, for UAT). The live-domain cutover is left as a documented step to run together (see SAFETY).
  - **B** — **multi-mechanism exposure**: detect internet exposure via nginx **and** Caddy **and** Cloudflare Tunnel (cloudflared, used on N150) **and** direct/firewall — and report the mechanism + public hostname. Build as pluggable detectors per category.
- Work slowly/carefully, test as many times as needed.

## SAFETY (why the live cutover is NOT done overnight)
The dockerized stack will run **in parallel** (own port/Mongo) without touching the
live native install (systemd `infradocs-v6-api.service` + host nginx serving
infra.ocialwaysfree.site). The final swap (stop native → repoint domain → docker
serves it) is irreversible; doing it unattended while the Cockpit session could drop
mid-swap risks leaving the live site down. So it's left as a tested, documented
one-liner for the morning. (The permission guardrail also blocks autonomous prod swaps.)

## Plan / progress  (✅ done · ⏳ in progress · ⬜ todo)
- ✅ A1. Storage containerized-mode: `INFRADOCS_HOST_ROOT=/host` → reads host mounts via /proc/1/mounts + statvfs. Native unchanged (4 mounts, 20 tests). Commit done.
- ✅ A2/A3/A5. Full compose stack (mongo + api host-access + Caddy web) built + DEPLOYED
  in parallel (ports 8081/8443/8090/27018). Smoke test PASSED: 424 assets, 9 apps,
  69GB storage, 29 ports, UI served over TLS + /api proxy, auth required. Running now
  via `docker compose -f deploy/docker/docker-compose.yml --env-file deploy/docker/.env`.
- ✅ (bonus) Fixed API scan job to build ports+storage registries (was agent-only) —
  fixes "Scan now is incomplete" for native AND docker (storage was 0). commit b55ce46.
- ⏳ A4. Env-overridable server_id/projects_root/db/username (config_loader._env_override
  + compose env + .env.example). Done in code; needs suite + final docker rebuild.
- ✅ B1. Caddy detector (app/scanners/caddy.py) — Caddyfile reverse_proxy parse. commit 85ba808.
- ✅ B2. Cloudflare Tunnel detector (app/scanners/cloudflared.py) — ingress parse. commit 85ba808.
- ✅ B3. Correlator Pass 6c unifies nginx ∪ caddy ∪ cloudflare_tunnel → app.exposure[]
  (+ internet_exposed + public URL). nginx now flows through the same _expose helper.
- ✅ B4. 10 new tests (test_exposure_detectors.py + correlator exposure test). Both
  detectors run clean on OCI (0 — OCI has no host caddy/cloudflared; live-test on N150).
- ⬜ Z. Final handoff: deploy/cutover commands + UAT instructions.

## Facts (don't re-derive)
- PoC verdict: dockerizing works. From inside the container (host net+pid, docker.sock,
  /run/systemd+/run/dbus, host mounts): systemd 305, docker, ports, compose, cron, certs
  all correct. nginx needs the nginx binary in the image (added). storage needs host-root.
- Image: `deploy/docker/Dockerfile` → `infradocs-api:poc` (586MB).
- Multi-server SSH (later): see memory `multi-server-ssh` — OCI/OCI-P/N150 only;
  N150 user `manishkumarsinha`, key `~/.ssh/master_key`.

## ☀️ MORNING GUIDE (read this first)

### What's running right now
- **Live site UNTOUCHED**: infra.ocialwaysfree.site still served by the native install
  (systemd `infradocs-v6-api.service` :8004 + host nginx). I did NOT touch it.
- **NEW: the dockerized product runs in PARALLEL** on alt ports (no conflict):
  - web (Caddy + UI):  http 8081 / https 8443
  - api:               8090   ·   mongo: 27018
  - bring up/down: `docker compose -f deploy/docker/docker-compose.yml --env-file deploy/docker/.env {up -d|down}`
  - login: `msinha` / `smoketest123` (test creds in the gitignored deploy/docker/.env)

### A) UAT the dockerized product (before any cutover)
From your laptop, tunnel to it then browse (self-signed cert on localhost, accept it):
```
ssh -i ~/.ssh/master_key -L 8443:localhost:8443 msinha@<OCI>     # OCI = biwi? no, this host
# then open https://localhost:8443  (login msinha / smoketest123)
```
(or, if your laptop is on Tailscale: https://100.107.140.36:8443). Click around —
it ran a real scan of THIS host from inside the container: all 8 scanners, ~424
assets, 9 apps, 69 GB storage, the Kill Button, blast radius, etc.

### B) The product itself (for any Ubuntu server / your colleague)
`deploy/docker/` is a self-contained stack. On a fresh host:
```
git clone <repo> && cd <repo>/deploy/docker
cp .env.example .env      # set DOMAIN=infra.example.com, ADMIN_PASSWORD, SERVER_ID, PROJECTS_ROOT
docker compose up -d
```
With a real DOMAIN, Caddy auto-provisions Let's Encrypt TLS on 443. One image,
env-driven — deploys anywhere. (Proven: all scanners see the host from the container.)

### C) Cutover on THIS OCI box — two options (your call; do together when up)
This host's nginx fronts MANY domains (home/dashboard/chat…), so the full-Caddy
takeover would disrupt the others. Recommended = the MINIMAL cutover:

**C1 — Minimal (recommended): dockerize the backend, keep host nginx as the front.**
  1. Point the infra vhost's /api at the docker API instead of the native one:
     edit /etc/nginx/sites-enabled/infra.ocialwaysfree.site → `proxy_pass http://127.0.0.1:8004/api/`
     becomes `http://127.0.0.1:8090/api/`; `sudo nginx -t && sudo systemctl reload nginx`.
     (Run the docker stack with API_PORT=8090; the frontend stays served by host nginx.)
  2. Stop the native API: `sudo systemctl disable --now infradocs-v6-api.service`.
  → Lowest risk; other sites untouched; backend now dockerized + auto-restart.

**C2 — Full self-contained takeover:** only if you migrate the OTHER domains to the
  bundled Caddy too (set WEB_PORT=80/WEB_TLS_PORT=443, add their reverse-proxy rules
  to the Caddyfile, stop host nginx). More work; do deliberately.

Either way, ARCHIVE the native install after: it's just `frontend/dist` + `venv` +
the systemd unit — keep them aside, nothing is deleted.

### Notes / follow-ups
- Caddy redirects http→https even for localhost (cosmetic); UAT over :8443.
- Exposure detectors (caddy/cloudflared) find 0 on OCI (it uses nginx) — they'll
  light up on N150 (cloudflared). Live-test there once N150 is onboarded.
- The multi-server (SSH to OCI-P/N150) work is the NEXT phase, not done tonight.

## Progress log
- (start) handoff doc created.
- A: storage containerized-mode, full compose stack (mongo+api+caddy), scan-job
  registry fix, env-overridable config. Built + deployed parallel + smoke-tested.
- B: caddy + cloudflared exposure detectors + correlator Pass 6c (unified exposure).
- Suites green throughout (184). Everything committed + pushed to feature/neon-depth-theme.
