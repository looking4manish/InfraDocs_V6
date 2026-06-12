# InfraDocs V7 — Master Plan

> **Purpose of this file:** single source of truth for the V6 → V7 evolution. To resume work in any
> new session, attach this file and say: *"Resume InfraDocs V7 at Phase N, Step X. C.H.A.I.N. protocol."*
> Update the Status line and checkboxes as phases complete.

- **Status:** Planning complete — Phase 1 not started
- **Last updated:** 2026-06-11
- **Repo:** `/home/msinha/projects/InfraDocs_V6` (OCI, user `msinha`)
- **Live:** https://infra.ocialwaysfree.site · API `:8004` (FastAPI, Basic Auth) · Frontend React 19 + Vite 8 + Tailwind 3
- **Protocol:** C.H.A.I.N. — one action per turn, State Block every turn, no assumed filenames

---

## 1. Vision

Evolve InfraDocs from a passive single-host inventory into a **continuous discovery, relationship,
and self-healing cockpit** for the whole lab (OCI, OCI-P, N150, OMEN). Three new engines on top of V6:

1. **Discovery** — scanners run on a timer on every host; a diff engine turns snapshots into typed
   events (`asset.discovered`, `port.changed`, `asset.vanished`).
2. **Relationships** — the correlator persists *evidence* (`links[]`) for every join it makes;
   the UI renders topology, never re-derives it.
3. **Heal** — policy-driven probes + actions with locks, backoff, rate limits, audit trail.
   Dry-run for one week before activation. rs0 members default to notify-only.

---

## 2. Recon findings (Phase 0 — complete)

Verified against the live repo and a real application document (`openwebui`, fetched 2026-06-11):

- **The correlator's 11 passes compute relationships then discard them.** App docs store name
  lists only (`containers: ["openwebui"]`); no edges, no evidence. Biggest backend/UI gap.
- **App docs are hollow at the component level.** Container state/health, nginx `upstream_port`,
  SSL `not_after` live only on asset docs — the topology UI needs them denormalized.
- **Scans were 18 days stale** (`updated_at: 2026-05-24`). `deploy/` has an API service but **no
  agent timer unit**. Scans are manual-only today.
- **V6 is single-host.** `server_id` is hardcoded `oci` (kept in `application_id =
  {server_id}:app:{name}` for forward-compat — no migration needed for multi-host).
  N150/OMEN assets (incl. everything behind `chat.ocialwaysfree.site`-class domains hosted
  elsewhere) are invisible by design, not by bug.
- **Cross-host dependency hiding in env keys:** openwebui carries `OLLAMA_BASE_URL` → Ollama on
  OMEN. Values are (correctly) never stored; a future pass can emit a "declared dependency,
  target unknown" dashed edge from the key name alone.
- Correlation strength order (keep): compose label → WorkingDir → systemd FragmentPath →
  nginx proxy_pass→port index → DOMAIN_MAPPING → /proc cwd. Project attribution rule:
  only `~/projects/<X>` paths name a project; everything else is `System`. Never regress to
  service-name inference (V5 false-projects bug; tests guard it).

---

## 3. Asset gap analysis (what V6 cannot name)

Pattern: V6 inventories everything that *serves*, almost nothing that *protects, schedules, or connects*.

| # | Gap | Why it matters | Scanner | Effort |
|---|-----|----------------|---------|--------|
| 1 | Database topology | rs0 (3 hosts, 1 primary) is the most critical asset and is invisible. `rs.status()`, sizes, data paths. Also PostgreSQL (OCI + Neon). | new `db.py` | M |
| 2 | Exposure surface | Cross-check listening ports × ufw/iptables × OCI security lists/route tables. Turns `internet_exposed` from hearsay into proof. Is `:27017` on OCI-P reachable? | new `exposure.py` | M |
| 3 | Backup coverage | Nothing inventories whether anything is backed up. Jobs + last-run + target. Highest-value single addition. | new `backup.py` | M |
| 4 | Cron jobs | User + system crontabs invisible (systemd timers already captured). | `cron.py` | S |
| 5 | Tailscale mesh | The lab's nervous system. `tailscale status --json`: devices, IPs, online state. | `tailscale.py` | S |
| 6 | Cloudflare DNS + tunnels | Authoritative domain→origin map. Reconciles DNS ↔ vhosts ↔ tunnel ingress. Catches orphaned DNS + shadow vhosts. Read-only token. | `cloudflare.py` | M |
| 7 | Unmanaged processes | Listeners owned by neither systemd nor docker (nohup/tmux) → flag "won't survive reboot". | classify in `port.py` | S |
| 8 | Docker hygiene | Dangling images, orphaned volumes, exited-with-restart=always. **Zero new scanning** — correlator pass. | correlator | S |
| 9 | Git state per project | Dirty files + unpushed commits per `project_dir`. "Is what's running committed anywhere?" | `git.py` | S |
| 10 | Certificates registry | Promote cert expiry (nginx SSL, LE paths, CF origin) to first-class registry + timeline. | extend `nginx.py` | S |
| 11 | Reboot resilience score | Per-app: restart policies + enabled units. **Zero new scanning** — correlator pass. | correlator | S |
| 12 | Host runtime facts | Kernel, distro, docker version, pending updates, uptime. | `host.py` | S |

### Substrate layer (approved 2026-06-11)

Root-of-infrastructure data beneath the OS:

- **Oracle (OCI + OCI-P), two stages:**
  - *Stage 1 — IMDS:* `http://169.254.169.254/opc/v2/instance/` — shape, OCID, region, VNICs,
    public/private IPs. Zero credentials. Ships in wave 1.
  - *Stage 2 — SDK with instance-principal auth:* VCN, subnets, route tables, security lists,
    NSGs, attached block volumes. Setup: dynamic group matching both instances + read-only
    policy (`read virtual-network-family / instance-family / volume-family`). **No API keys on
    disk — ever.** Ships with `exposure.py` (two halves of one proof).
- **N150 hardware truth:** `smartctl` SMART health (early warning for Nextcloud/Immich data),
  `sensors`, `dmidecode`, `lsblk`, `ip route`. New `hardware.py`. Deco router: skip (no usable
  API). AdGuard Home local API: optional, later.
- Naming: layer = `substrate`; categories `cloud_instance`, `cloud_volume`, `cloud_vnic`,
  `security_rule`, `route_table`, `hw_disk`, `hw_sensor`. Avoids the OCI-server vs OCI-cloud
  name collision. Substrate scans **daily**, not 6-hourly.
- Storage registry enrichment: mount ↔ block volume OCID mapping.

---

## 4. UI specification

**Principles:** (a) navigate by *lens*, not by feed — same graph, four projections; (b) everything
reachable in 2 keystrokes (⌘K) or 2 clicks; (c) every entity renders its relationships, not just
fields; (d) emerald/amber/red reserved strictly for state. Preserve the V6 dark palette
(`#0b1220 / #111a2e / #16213e / #1c2a4a`, accent `#3b82f6`).

### Home = lens tabs
`Projects · Servers · Resources · Assets · Map(link)` + ⌘K + slim expandable attention banner
(1 line: "1 critical · 3 warnings"). Counts demoted to footer.

- **Projects lens:** card grid — health dot, server chip, primary URL, mono micro-stats
  (`1 ctr · :3000 · 2.1 GB · git ±14`). Attention-sorted. **Ghost cards** (dashed) for apps known
  from DNS but unclaimed by any agent ("deploy agent to claim") — turns missing coverage into
  visible UI.
- **Servers lens:** grouped by host; server cards carry substrate facts (shape, IPs, disks, SMART).
- **Resources lens:** registry hub tiles — Ports, Storage, Domains & certs, Databases, Schedules,
  Backups — one headline stat each.
- **Assets lens:** the existing flat power-table, kept.

### Three primitives (everything sits on these)
1. **⌘K command palette** — fuzzy search across all collections + actions (with confirm).
   Typing `3000` finds the port, the container behind it, and the nginx block in front of it.
2. **Universal detail drawer** — every asset row anywhere opens the same right-side drawer:
   identity, state, mini relationship lane, `links[]` evidence, action buttons. No dead-end pages.
3. **Freshness header** — per-server last-scan pill, permanent. Amber > 12 h, red > 48 h.

### Hero pages
- **ApplicationDetail = topology lane.** URL → nginx (SSL badge, exposure) → host port →
  container (state/health/restart) → storage. Evidence chips on connectors, link-evidence panel
  below, action audit strip in footer. Single API call (needs Phase 1 fields). Multi-container
  apps upgrade the lane to a small graph (React Flow).
- **Map.** Server regions as containment; app nodes with health dots; solid blue = routing edges
  (with port labels); dashed amber = declared dependencies (from env-key names); System as dashed
  catch-all strip; pending hosts render as dashed regions listing DNS-known residents. Edge-type
  filter chips (routing / storage / data). Phase 5+: substrate toggle (VCN/subnet/volume view).
  Click → drawer, double-click → application page. React Flow, lazy-loaded on its route.

### Chrome decision
**Top-nav, no sidebar** (lens tabs + ⌘K replace it). Activity pages (Scans, Actions, Heal log)
live under a small overflow/Activity menu. *(Open: confirm after living with it one phase.)*

---

## 5. Build phases

- [ ] **Phase 1 — Correlator v2 + heartbeat** *(backend, ~2 sessions)*
  - `links[]` evidence: every pass appends `{src_kind, src, dst_kind, dst, via, pass}`
  - `containers_detail[]` (name, image, state, health, restart_policy, host_ports)
    and `nginx_detail[]` (server_name, listen_ports, upstream_port, ssl_not_after,
    internet_exposed, cloudflare_origin, url) — **additive**, name lists stay, nothing breaks
  - Hygiene pass (gap 8) + reboot-resilience pass (gap 11)
  - systemd timer for the agent (6 h) — fixes the 18-day-stale store
  - Extend fixture tests per pass
- [ ] **Phase 2 — Frontend foundation** *(~2 sessions)*: ⌘K palette · universal drawer ·
  freshness header · attention rules v1 (over existing data only: restart-policy gaps,
  SSL expiry, orphan ports, staleness)
- [ ] **Phase 3 — Hero pages** *(~2–3 sessions)*: lens home + ApplicationDetail topology lane
- [ ] **Phase 4 — Scanner wave 1**: `db.py` · `exposure.py` (+ substrate stage 2 SDK) ·
  `backup.py` · `cron.py` · substrate stage 1 IMDS · `hardware.py` (N150) · registry pages
- [ ] **Phase 5 — Map** (React Flow, lazy route — the 9B code-split slot)
- [ ] **Phase 6 — Multi-host**: agents on N150 + OMEN (`server_id` per host, same Mongo URI over
  Tailscale) · server switcher · ghost cards go live · scanner wave 2 (`tailscale.py`,
  `cloudflare.py`, `git.py`, certs registry, `host.py`)
- [ ] **Phase 7 — V7 engines**: diff engine → Changes page/feed · heal engine (policy schema,
  probes, executor with per-asset locks + rate limits, audit) — **dry-run 1 week**, rs0 =
  notify-only, then activate

**Sequencing rules:** every phase ships something visible; no frontend built twice; Phase 1's
`links[]` is the trust foundation for everything visual; Phase 6's agents are what make the lab
real — everything else is craft.

---

## 6. Phase 1 — opening steps

1. Read `app/correlator.py` lines 150–300 (passes 3–11) — modify surgically, not by guesswork.
2. Design `links[]` entry shape + where each pass emits it.
3. Implement `links[]` + `containers_detail[]` + `nginx_detail[]` in correlator (additive).
4. Add hygiene + resilience passes.
5. Extend `tests/test_phase5_correlator.py` fixtures; run full suite.
6. Add `deploy/infradocs-v6-agent.timer` + `.service`; install; verify next auto-scan.
7. Re-fetch `/api/applications/openwebui`; confirm new fields; update this file's checkboxes.

---

## 7. Key reference

| Item | Value |
|---|---|
| Hosts | OCI `80.225.195.84` / TS `100.107.140.36` · OCI-P `140.245.228.255` / TS `100.70.18.9` · N150 TS `100.72.146.5` · OMEN TS `100.98.102.10` |
| API | `http://localhost:8004` — Basic Auth user `msinha` (password never stored in docs) |
| Mongo | URI in `.env` as `INFRADOCS_MONGO_URI` (gitignored); collections `assets`, `applications`, `scan_logs` |
| Validated app doc | `oci:app:openwebui` — chain url→nginx→:3000→container→storage confirmed |
| Routers | `app/api/routers/{actions,applications,assets,health,ports,projects,scans,storage}.py` |
| Scanners (V6) | compose, docker, nginx, port, storage, systemd (`app/scanners/`) |
| Guard rails | No service-name project inference · env *values* never stored (key names only) · `infradocs-v6-*` services self-protected from actions (API 409s) |
| Secrets posture | Read-only scanning everywhere · OCI via instance principals (no keys on disk) · CF via read-only token |