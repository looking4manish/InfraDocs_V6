# Session Summary — Federation UI + Command Dispatch

**Branch:** `feature/federation-ui-and-dispatch` (off `feature/neon-depth-theme`)
**Status:** All three tasks complete, committed, and pushed. **Not merged** to `main`.
**Tests:** 212 passed (was 202; +10 new). Frontend compile-check (`vite build --outDir
/tmp/ifd-check`) clean. Production `frontend/dist/` was never touched.

---

## Task 1 — Housekeeping deletions (commit `e630b12`)

Removed point-in-time session records the context doc flags as HISTORICAL / build journal:

- `HANDOFF_2026-06-23_neon-ia-actions.md`, `OVERNIGHT_HANDOFF.md`, `V7_PHASE35_HANDOFF.md`
  — all three carry an explicit "🗄️ HISTORICAL" banner; their work is on `main`.
- `docs/phases/PHASE_{1..8,9A}_STATUS.md` (9 files) — the build journal, superseded by the
  living docs. `docs/phases/` is now empty.

Also updated the single live reference to those files — `CONTEXT.md` §6 "History of a past
session" breadcrumb — to point at `git log` instead of the now-removed paths.

Nothing under `app/`, `tests/`, `frontend/src/`, `deploy/`, the README, or the protected
living docs was touched.

## Task 2 — Federation viewing UI (commit `b25dd60`)

Replaced the static `HOSTS` mock in the Servers lens (`frontend/src/pages/LensHome.jsx`)
with a real, data-driven view:

- **Server list** = the primary (identity from `/api/health`) + every secondary that has
  pushed (`/api/federation/servers`). Each card shows online/stale status, app/asset counts,
  role, and last-seen. The primary is never double-listed if it also appears in
  `federation_servers`.
- **"Add a server"** mints a join token via `/api/federation/tokens` and shows the operator
  the token + this primary's URL + enrollment steps (run the setup wizard as a `secondary`).
- **Server switcher** — chips persisted in `?server=<id>`; scopes the lens to one host or All.
- API client gained `federationServers()` and `mintFederationToken()`.

Styling reuses existing `neon-panel` / `Fact` / chip patterns — no new design language.

## Task 3 — Command dispatch, Model A (commit `2845b0b`)

Primary→secondary action dispatch, built **NAT-friendly** to match the existing
outbound-push model: a queue the secondary polls outbound (it is never reached inbound).

**Flow:** primary enqueues → secondary claims on poll → executes via the *existing* guarded
`app.actions.dispatch` → reports result back → primary audits in `actions_log`.

Backend (`app/api/routers/federation.py`):
- `POST /api/federation/commands` — enqueue `{server_id, asset_id, action, args}`; refuses
  `infradocs-v6-*` with **409** before queuing; writes a `pending` audit row.
- `GET /api/federation/commands` — list recent commands (drives the UI panel).
- `POST /api/federation/commands/pending` — secondary atomically *claims* its pending
  commands (`find_one_and_update` → `dispatched`); token-scoped; no double-claim.
- `POST /api/federation/commands/{id}/result` — secondary reports outcome; primary closes
  the command and writes the final audited row. Token must be scoped to the command's server
  (else **403**).

Secondary side:
- `app/federation.py` `poll_and_execute()` — pull → `dispatch()` (same allow-list +
  self-protection as local actions: `SelfActionRefused` → `refused`, `ActionNotAllowed` →
  `failed`) → push result. All outbound. New `_post_json` helper; `push_to_primary` unchanged.
- `app/federation_agent.py` — `python -m app.federation_agent poll`; reads the secondary
  config the wizard wrote (`settings.role/primary_url/join_token`) and runs one cycle.
- `db_manager.create_indexes()` — indexes for the `federation_commands` queue.

Frontend: selecting a secondary in the Servers lens reveals a **"Remote actions"** panel —
dispatch by asset id + action, plus a live (4s auto-refresh) list of dispatched commands with
status badge and stdout/stderr. Client gained `dispatchFederationCommand()` /
`listFederationCommands()`.

Tests (`tests/test_federation_dispatch.py`, 10): `poll_and_execute` success /
self-protect-refused / not-allowed (mocked outbound); enqueue happy-path + audit, unknown
server/asset 404, self-protect 409; claim token-gating + no-double-claim; full
claim→result round-trip audit; cross-server token 403.

---

## Decisions & assumptions

- **Model A = poll, not push.** The primary cannot reach a NAT'd secondary, so dispatch is a
  queue the secondary drains outbound. This is the only model consistent with the existing
  federation design; a push model would break for N150-style hosts.
- **Self-protection enforced twice** — fast 409 at the primary's enqueue endpoint *and* at the
  secondary's `dispatch()` (defense in depth). The enqueue check matches on the asset name
  prefix; the canonical enforcement remains `app.actions`.
- **Embedded asset payload.** The command carries a snapshot of the target asset
  (category/name/metadata) captured at enqueue time. The secondary's dispatcher resolves
  containers by `container_id` first, falling back to name — see "left for review" below.
- **Audit lives on the primary.** `actions_log` on the primary is the fleet's single audit
  trail (a `pending` row at enqueue, a final row at result, both tagged `origin: "federation"`
  + `command_id`). The secondary does not separately persist these.
- **Server switcher scope.** It currently scopes the Servers lens only (URL-shareable). Wiring
  it to globally filter Projects/Web was deliberately left out to avoid cross-lens churn.

## Left for human review before merge to `main`

1. **No secondary poll loop is scheduled.** `federation_agent poll` runs one cycle; nothing
   cron's it yet. A secondary won't pick up commands until that's scheduled (systemd timer /
   cron / `/loop`). Decide cadence vs. responsiveness.
2. **Stale `container_id`.** If a container is recreated on the secondary between scan and
   dispatch, the embedded `metadata.container_id` goes stale and `dispatch()` would 404 on it.
   Options: re-resolve by name on the secondary, or have the secondary look the asset up in its
   own DB by `asset_id`. Low-risk for systemd (resolved by stable name).
3. **No command TTL / cleanup.** `federation_commands` grows unbounded and a command claimed
   but never reported stays `dispatched` forever. Consider a TTL index or a reaper.
4. **REGISTRY_SPEC.md** at repo root was intentionally kept (it's referenced by the CONTEXT.md
   Actions breadcrumb, not a handoff/journal file).
5. **Chunk-size warning** from `vite build` (>500 kB) is pre-existing, not introduced here.
6. **API tests need a reachable MongoDB** (they `pytest.skip` otherwise) — same as the existing
   Phase 8 API suite. They ran green here.

---

# ⚠ LIVE-HOST CHANGES — REVIEW

Session goal: schedule the two federation cycles (`poll` on secondaries, `reap` on the
primary) as role-detected systemd timers, and install them across the OCI / OCI-P / N150
tailnet mesh. **Outcome: no host currently has a configured federation role, so by the
role-detection rule NO timer was installed on any host.** The only live change is undoing a
prior premature install. Details per host below.

### Step 1 — premature timer DISABLED (OCI)
A previous session had installed **and enabled** `infradocs-fed-reap.timer` on OCI even though
OCI's `settings.role` is `None`. That was wrong (reap must run only on the primary). This session:
- `sudo systemctl disable --now infradocs-fed-reap.timer` → `Removed .../timers.target.wants/infradocs-fed-reap.timer`, now `disabled` + `inactive`.
- Confirmed gone from `systemctl list-timers` (no `infradocs-fed` timers).
- Then removed the leftover inert unit files and `daemon-reload`d, so OCI carries nothing.

### OCI — detected role: **None (unconfigured)** → installed: **NOTHING**
- Role read locally: `OCI role = None`.
- Action: nothing installed; leftover `infradocs-fed-reap.{service,timer}` removed.
- Verify:
  - files: `(no infradocs-fed unit files — clean)`
  - timers: `(no infradocs-fed timers — clean)`
  - untouched: `infradocs-v6-agent.timer` still scheduled (next 2026-06-27 20:26 UTC); `infradocs-v6-api.service` = `active`.
- **Operator TODO:** run the setup wizard on OCI to assign its role (this is intended to be the
  PRIMARY). Once `role=primary`, install reap per `deploy/systemd/INSTALL.md`.

### OCI-P — reachable, but **no InfraDocs install** → installed: **NOTHING**
- SSH `msinha@100.70.18.9` (master_key) OK; `hostname = oci-p`.
- `repo: ABSENT`, `venv: ABSENT` — InfraDocs isn't deployed here, so there's no role to read
  and no interpreter to run a timer against.
- Action: nothing installed.
- **Operator TODO:** deploy InfraDocs on OCI-P, run the setup wizard (→ `role=secondary`,
  primary URL, join token), then install poll per INSTALL.md.

### N150 — reachable, but **InfraDocs V6 not deployed (V5 only)** → installed: **NOTHING**
- Reachable over the tailnet as **`manishkumarsinha@100.72.146.5`** (not `msinha`), key
  `~/.ssh/master_key`; `hostname = N150`. (An earlier attempt as `msinha@` was rejected — the
  username, corrected mid-session, was the blocker, not the network.)
- InfraDocs V6 is **not deployed**: `~/projects/InfraDocs_V6` is absent; only the legacy
  `~/projects/InfraDocs_V5` checkout exists, and no V6 venv. So there is no V6 `settings.role`
  to read and nothing for a V6 timer's `ExecStart` to run against.
- A stale legacy `infradocs-scanner.timer` (V5-era, `inactive`/`dead`) is present — **left
  untouched** (not one of our four `infradocs-fed-*` units).
- Action: nothing installed (host not provisioned for V6 — not a failed install).
- **Operator TODO:** deploy InfraDocs V6 on N150, run the setup wizard (→ `role=secondary`,
  primary URL, join token), then install poll per `deploy/systemd/INSTALL.md`. SSH as
  `manishkumarsinha@100.72.146.5`.

### Guardrails honored
Only `infradocs-fed-*` units were ever touched. `infradocs-v6-agent.timer`,
`infradocs-v6-api.service`, nginx, Caddy, and cloudflared were not modified or restarted on any
host. No half-installed/broken state was left or pushed: every host carries either its correct
units (none qualified this run) or nothing.

### Bottom line
The scheduling machinery is built, committed, and role-safe (both cycles self-guard; install is
role-detected). It is **not yet live anywhere** because the fleet has no roles assigned. The
gating next step is operator-side: run the setup wizard to make OCI the primary and OCI-P/N150
secondaries, then install per `deploy/systemd/INSTALL.md`. This supersedes "Left for human
review" items 1 and 3 above (the reaper and the timers now exist).

---

# ═══ DIRECT FEDERATION + LEASE ELECTION (2026-06-28) ═══

Branch `feature/direct-federation-lease-election` (off `main`). **Code only — not
merged, not deployed, no live host touched.** Replaces the NAT-era outbound
command-queue model with a direct (Tailscale-mesh) one.

## Removed (commit `b920d35`)
The whole queue/poll/reap control plane, obsolete on a mesh where every node is
directly reachable:
- federation router: `/commands`, `/commands` (list), `/commands/pending`,
  `/commands/{id}/result`, `reap_stale_commands`, `COMMAND_EXPIRY_SECONDS`.
- `poll_and_execute()` (app/federation.py); `app/federation_agent.py` (poll+reap CLIs).
- `deploy/systemd/infradocs-fed-{poll,reap}.*` + INSTALL.md; the `federation_commands`
  indexes; the frontend Remote-actions panel + its client calls;
  `tests/test_federation_dispatch.py`.
- **Kept:** the data plane (`POST /ingest`, `push_to_primary`), token mint, server
  list, and the guarded actions dispatcher + self-protection (`app/actions.py`).

## Added

**Bidirectional reachability at enroll (commit `38ce943`).** A secondary enrolls
only if reachability proves out BOTH ways:
- `POST /api/federation/enroll` (token-auth): the request arriving proves
  secondary→primary; the primary then connects BACK to the secondary's advertised
  address (`GET /api/federation/ping`) to prove primary→secondary. Records the
  enrollment (with the secondary's URL) ONLY if both pass; returns a per-direction
  verdict + readable reason otherwise.
- `GET /api/federation/ping`: unauth identity + lease view (the back-connection target).
- Secondary side: `ping_node()` + `enroll_with_primary()`; an unreachable primary
  is reported as `secondary→primary=False` rather than raising.
- Wizard `/complete`: a secondary must pass the handshake (needs `advertise_url`) or
  it's refused 400 with the per-direction detail; the UI shows ✓/✗ per direction.

**Mongo-lease leader election + manual promote (commits `38ce943`, `38f1b27`).**
- `app/cluster_lease.py`: one doc (`cluster_lease`, `_id="leader"`). Acquire/renew is
  a single atomic `find_one_and_update` matching only *expired-or-mine*; with the
  unique `_id` that is the entire split-brain guard (no heartbeats/terms). On leader
  death the lease expires and a peer acquires on its next tick — automatic failover.
- Gated background renewer in the API lifespan (`lease_enabled=false` default → inert
  until a fleet enables it); `settings.primary_node` follows the lease holder.
- `POST /api/federation/promote` (manual): refuses if any reachable node reports a
  live leader; if some nodes are UNREACHABLE it returns `needs_force` + a
  two-primaries warning instead of promoting; `force=true` seizes only behind that
  explicit confirm, and NEVER against a confirmed-live leader. UI surfaces the
  current leader + the guarded promote/force flow.

## Lease defaults (and why)
`lease_ttl_seconds=15`, `lease_renew_seconds=5` (config + config.yml). The leader
renews 3× per TTL, so a single missed renewal (a brief blip) does **not** trigger
failover; it takes ~2 consecutive misses (~10–15s) for a peer to take over. Tight
enough for quick recovery, loose enough to avoid flapping. `lease_enabled=false` by
default so merging/installing this code changes nothing until a fleet opts in.

## Tests
`tests/test_federation_direct.py` (20, all pass): enroll both-pass / either-fail /
bad-token / identity-mismatch + wizard wiring; lease first-acquire / no-steal /
exactly-one-winner / renewal-extends / expiry-failover / old-leader-steps-down /
force / release; promote refuse-live-leader / allow-none / needs-force-on-unreachable
/ force-acquire / force-still-refused-vs-confirmed-leader.

## ⚠ REVIEW BEFORE DEPLOY
1. **Lease timing (TTL 15s / renew 5s).** This is the failover-vs-flapping knob and
   assumes all nodes share one MongoDB reachable over the tailnet with roughly synced
   clocks (the atomic write is server-side, so modest skew is fine, but wildly wrong
   clocks would misjudge `expires_at`). Confirm the numbers fit the real mesh latency
   before enabling `lease_enabled`.
2. **The manual force path (`promote force=true` / `force_acquire`).** This is the one
   place that bypasses the atomic guard and CAN create two primaries if the old leader
   is actually alive but unreachable. It's reachable only behind an explicit operator
   confirmation and never against a confirmed-live leader — but a human pressing
   "Force promote anyway" during a partition is the residual two-primary risk. Verify
   the UI warning copy and consider whether a fence (e.g. step-down on lease-loss
   detection) is wanted before relying on it in production.

Not merged. Not deployed.

---

# ═══ PRIORITY-RANKED GOSSIP CLUSTER + FAILOVER (2026-06-28) ═══

Branch `feature/priority-failover-cluster`. **Code only — not merged, not deployed, no
live host touched.** Replaces the Mongo-lease election with a priority-ranked,
gossip-based cluster that coordinates purely node-to-node (every node runs its OWN Mongo
— NO shared coordination DB).

## ⚠ Base-branch decision (read first)
The task said "branch off current main", but also "KEEP the bidirectional reachability
enroll gate + the manual promote control" and "REMOVE app/cluster_lease.py" — all of
which live only on `feature/direct-federation-lease-election`, which was **never merged
to main**. Branching off bare `main` would lose the KEEP items and make the REMOVE a
no-op. I therefore branched off `feature/direct-federation-lease-election` (= main + the
direct-federation work), the only base where the REMOVE/KEEP instructions are coherent.
**If `main` was supposed to already contain that work, merge it first and rebase this.**

## Removed
`app/cluster_lease.py` + the lifespan lease renewer + the lease-based `/federation/leader`
and `/federation/promote` + the lease config. (The queue/poll/reap was already gone.)

## Added
- **`app/cluster.py` (pure, the core):** reachability, `has_majority` (strict),
  `evaluate_cluster()` returning one of stay/frozen/follow/promote_self/step_down/
  wait_election/no_leader; `merge_gossip` (roster self-heal, incl. transitive peer
  learning); `priority_in_use`; `current_leader_address`.
- **`app/cluster_manager.py` (gated, default off):** the 10s gossip loop — pull every
  peer's `/api/cluster/health`, self-heal the roster, run `evaluate_cluster`, apply
  (become/relinquish primary). Tracks the one-round election grace.
- **`app/api/routers/cluster.py`:** `/health` (gossip msg), `/state` (UI), `/override`
  (pin), `/promote` (guarded restore path).
- **Priority on enroll:** `/federation/enroll` carries a priority; the primary REJECTS a
  duplicate (409 "priority N already in use") and adds the node to its roster. First node
  (primary/standalone) auto-gets priority 1 + is_primary; a secondary picks a free one.
- **Data sync:** after a scan a non-primary pushes to the CURRENT leader (follows gossip,
  retargets after failover) via the existing `/ingest` — no shared DB.
- **UI serving:** app-level 302 leader redirect (API root + a `ClusterRedirectGate` in
  the SPA) — no VIP/keepalived. Servers lens shows nodes/priorities/leader/override/
  reachability; Setup takes a priority.
- **Config:** `cluster_enabled` (off), `health_interval_seconds=10`,
  `unreachable_after_seconds=30` (3 missed rounds).

## How the guarantees hold
- **Split-brain / no double-primary:** the MAJORITY GUARD is applied to *both* the
  incumbent (a primary that loses majority STEPS DOWN) and to any would-be electors (a
  minority partition never self-promotes). Election picks the lowest priority number in
  the majority — deterministic, so every majority node agrees on the same winner.
- **No auto-preempt / failback:** a node only elects when NO primary is visible; a
  recovered higher-priority node sees the live primary via gossip and `follow`s it.
  Reclaiming is the manual promote.
- **Override:** a remembered flag (gossiped from the primary) that returns `frozen` from
  `evaluate_cluster` regardless of primary reachability — freezes elections even when the
  primary appears lost.

## Tests (47 new, all pass)
- `test_priority_cluster.py` (15, pure): majority arithmetic; election elects
  highest-priority survivor + others defer; election grace; **minority must-not-elect**;
  **majority elects**; **partition never yields two primaries** (explicit 5-node split,
  asserts ≤1 primary); old-primary-steps-down; **no-auto-preempt**; two-primaries-on-heal
  lower-number-wins; **override freezes even when primary lost**; roster self-heal in one
  round + transitive.
- `test_cluster_endpoints.py` (9): first-node-primary + priority-1; priority uniqueness
  409 + range; promote refuse-vs-live / allow / **needs-force** / force; override; state.
- `test_federation_direct.py` (8): the priority-aware bidirectional enroll gate.

## REVIEW BEFORE DEPLOY — the four things a human must eyeball
1. **The MAJORITY GUARD (`app/cluster.py` `has_majority` + the step_down/no_leader paths).**
   This is THE split-brain guard. Confirm the strict-majority arithmetic and that the
   incumbent steps down on majority loss match your fleet size (esp. even-sized fleets,
   where neither half of a clean split has a majority → leaderless until a partition heals
   or an operator force-promotes).
2. **Partition / double-primary test results.** `test_partition_never_yields_two_primaries`
   asserts ≤1 primary across an explicit 5-node split. Eyeball that the modeled partition
   matches real failure modes (it tests the decision logic, not live network timing — the
   10s/30s timing + the gossip loop are integration glue, lightly covered).
3. **The override path.** A remembered flag that freezes ALL elections, even during
   apparent primary loss. If gossip never propagated the override before a partition, the
   two sides may disagree on whether it's set. Verify the operator workflow (set on the
   primary, confirm it's seen fleet-wide) before relying on it.
4. **The manual force-promote.** `/api/cluster/promote {force:true}` bypasses the
   live-primary refusal ONLY for unreachable (unconfirmable) peers — never against a
   confirmed-live primary — but a human force-promoting during a partition is the residual
   two-primary risk. Confirm the UI warning + that `current_leader_address`/redirect
   behave sanely with two primaries mid-heal (the lower priority number wins the conflict).

Also note: the gossip loop + data-sync + redirect are gated by `cluster_enabled=false`,
so installing this changes nothing until a fleet opts in. Not merged. Not deployed.

---

# ═══ TERMINAL INSTALLER + MERGE TO MAIN (2026-06-28) ═══

Two jobs. **Job 1 landed on `main`; Job 2 (the installer) is on a BRANCH, not main.**

## Job 1 — merge to main (DONE, pushed)
Merged `feature/priority-failover-cluster` (no-ff) into `main` → `origin/main` at
**`2826170`**, now containing direct-mesh federation + bidirectional reachability enroll +
the priority gossip cluster. Done in a worktree (live deploy dir untouched). Suite on
merged main: **233 passed, 1 failed** (only the known `test_integration_correlate_real_oci_scan`
openwebui drift).

## Job 2 — interactive terminal installer (on branch `feature/terminal-installer`)
A no-browser onboarding path; the browser wizard stays as the optional rich path feeding
the SAME config (`/api/setup/complete`).
- **`install.sh`** (repo root) — the one file the operator runs. Preflight (git/curl/docker
  + daemon) → clone/pull → prompts → write `deploy/docker/.env` → deploy → onboard → summary.
  On ANY failure it stops with a named reason and tears the stack down (`compose down -v`)
  so the box is left clean — never half-deployed.
- **`app/cli_install.py`** — the testable logic the script drives, reusing existing APIs (not
  reimplemented): priority uniqueness via `GET <primary>/api/cluster/health`; bidirectional
  reachability via `POST <local>/api/setup/complete` (→ `/federation/enroll`, primary connects
  back to this node's `/federation/ping`). Plus `.env` rendering + the non-interactive deploy
  invocation.
- **`deploy/docker/deploy.sh`** — added `INFRADOCS_NONINTERACTIVE=1`: reuse the pre-written
  `.env`, never prompt, and SKIP the browser-exposure menu entirely (no Tailscale).
- **Mesh-agnostic:** the installer never installs/assumes Tailscale or any VPN; the node is
  reachable at the operator-supplied ADDRESS, which is exactly what gets stored and what the
  leader-redirect points at (`current_leader_address` from the roster). Neutralized "tailnet"
  wording in the onboarding copy (Setup placeholder, enroll/advertise comments).
- **Tests (`tests/test_cli_install.py`, 13):** priority range + uniqueness rejection (mocked
  health), reachability-fail refusal surfacing per-direction verdict, priority-conflict reason,
  `.env` rendered correctly + no mesh assumption, primary/secondary body building, and the
  non-interactive deploy invocation (mocked subprocess).

## HOW TO INSTALL ON A NEW SERVER
On a fresh box (Docker + git + curl present), download and run the one file:
```bash
curl -fsSL https://raw.githubusercontent.com/looking4manish/InfraDocs_V6/main/install.sh -o install.sh
bash install.sh
```
(or `bash install.sh` from an existing checkout). You'll be asked:
- a short node id;
- **this node's reachable address** (e.g. `http://HOST-OR-IP:8081`) — any transport (VPN/VPC/LAN);
- whether this is the FIRST node (→ primary, priority 1) or a secondary;
- for a secondary: the **primary's address** + a **join token** (mint on the primary), and a
  **priority 1-99** — validated live: out-of-range or already-taken priorities are rejected,
  and enrollment is refused unless reachability proves out BOTH directions.
It then deploys the stack and onboards the node, ending with a summary (role, priority,
address, and for a secondary the confirmed-reachable primary). The dashboard is then at the
address you gave (login `admin` / the `.env` password — change it).

> Env overrides: `INFRADOCS_REPO_URL`, `INFRADOCS_DIR` (default `~/infradocs`), `INFRADOCS_BRANCH`
> (default `main`). A scripted/config-file path exists implicitly — install.sh just writes the
> same `.env` + calls the same `/api/setup/complete`; a non-interactive UX was not built this session.

## REVIEW BEFORE DEPLOY
1. **Residual transport mentions are cosmetic, not dependencies.** The browser wizard still
   OFFERS a "Tailscale" exposure choice and the IP-detector still LABELS tailscale/CGNAT
   addresses — both are conveniences, neither is required by onboarding or the installer.
   `deploy.sh`'s Tailscale path only runs in its INTERACTIVE mode (the installer always uses
   `INFRADOCS_NONINTERACTIVE=1`, which skips it). If you want the browser wizard fully
   mesh-neutral too, drop its tailscale exposure option separately.
2. **The installer was NOT run on any host** (operator UAT). It is syntax-checked (`bash -n`),
   its Python logic is unit-tested, but the end-to-end clone→deploy→onboard path has only been
   exercised in pieces. Run it on the first (primary) box, then a secondary, and confirm the
   bidirectional check + priority rejection behave live.
3. **Admin password.** The installer uses `admin` / `ADMIN_PASSWORD` from `.env`
   (default `Changeme001`) to drive `/api/setup/complete`; the operator must change it after.

**Installer landed on branch `feature/terminal-installer` (pushed), NOT on main.** Job 1's
merge IS on main. Not deployed anywhere.
