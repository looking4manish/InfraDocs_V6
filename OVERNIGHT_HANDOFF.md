# Overnight build — A (Docker product) + B (multi-mechanism exposure)

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

## Progress log
- (start) handoff doc created.
