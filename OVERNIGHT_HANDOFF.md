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
- ⬜ A2. `docker-compose.yml`: bundled Mongo + API (host mounts proven in PoC) + web.
- ⬜ A3. Web image: built frontend behind **Caddy** (auto Let's Encrypt from `DOMAIN`).
- ⬜ A4. `.env`-driven config + first-class admin password (no dev default).
- ⬜ A5. Full-stack smoke test (compose up on a spare port; scans + UI + an action).
- ⬜ B1. Caddy detector (parse Caddyfile reverse_proxy → host/upstream).
- ⬜ B2. Cloudflare Tunnel detector (cloudflared service/container + ingress config).
- ⬜ B3. Exposure-combining pass in the correlator (nginx ∪ caddy ∪ tunnel ∪ direct → per-service exposure + mechanism + public hostname).
- ⬜ B4. Tests + live verify.
- ⬜ Z. Update this handoff with deploy/cutover commands + UAT instructions.

## Facts (don't re-derive)
- PoC verdict: dockerizing works. From inside the container (host net+pid, docker.sock,
  /run/systemd+/run/dbus, host mounts): systemd 305, docker, ports, compose, cron, certs
  all correct. nginx needs the nginx binary in the image (added). storage needs host-root.
- Image: `deploy/docker/Dockerfile` → `infradocs-api:poc` (586MB).
- Multi-server SSH (later): see memory `multi-server-ssh` — OCI/OCI-P/N150 only;
  N150 user `manishkumarsinha`, key `~/.ssh/master_key`.

## Progress log
- (start) handoff doc created.
