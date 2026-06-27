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

# ═══ OVERNIGHT SESSION (2026-06-27) — appended ═══

_Full standalone copy: [`OVERNIGHT_REPORT.md`](OVERNIGHT_REPORT.md). Reproduced here so this summary stays self-contained._

# InfraDocs — Overnight Report (2026-06-27 → morning)

## TL;DR

- ✅ **Step 1 done:** `feature/federation-ui-and-dispatch` merged into **`main`** (no-ff) and
  pushed. Full suite on merged main: **215 passed, 1 failed** — the one failure is the
  known-unrelated `test_integration_correlate_real_oci_scan` (live openwebui drift).
- ⛔ **Steps 2–4 STOPPED — not safe to do unattended.** Investigation surfaced blockers the
  plan didn't anticipate (below). No live host state was changed beyond the pre-staged clone
  on OCI-P. The fleet is in its last-good state.
- 📋 **Morning work is teed up:** `deploy/OCI-P_MORNING_DEPLOY.md` (full runbook) + the
  checklist below. The pivotal first move is operator-only.

---

## Why Steps 2–4 were stopped (evidence)

1. **The live OCI primary runs OLD code.** `infradocs-v6-api.service` (started 2026-06-24)
   serves `/api/health` 200 but **`/api/federation/servers`, `/api/federation/commands`,
   `/api/ai/status`, `/api/setup/status` all return 404.** The federation endpoints a
   secondary must reach (mint token / ingest / commands) **do not exist on the live primary**.
   Making OCI a working primary requires **restarting `infradocs-v6-api.service`** onto current
   code — a **hard-forbidden** action this session. → Steps 3 & 4 cannot complete.
2. **The `infradocs` DB lives on the OCI-P production replica set.** The Mongo URI is a
   replica set across `100.70.18.9` (OCI-P) + `100.72.146.5` (N150) (+ OCI). So every
   federation write (role, tokens, commands) would land on the **production cluster whose
   primary is OCI-P** — the box I must not disturb. Writing role/tokens there gains nothing
   while the live API can't serve federation anyway.
3. **Docker product ⇄ host-venv poll-timer gap.** N150/OCI-P deploy = the docker product
   (containers, no host venv). But `infradocs-fed-poll.timer` runs `…/venv/bin/python` on the
   **host**. There is no committed way to run poll against a containerized deploy; bridging it
   (docker-exec, or a parallel host venv) is an **architecture decision**, not something to
   improvise unattended. Documented as a flagged choice in the runbook.
4. **`deploy.sh` is interactive** (prompts for docker-install, ids, exposure; may run
   interactive `tailscale up`) — not built for unattended execution.

Per the session's own rule ("if any step is ambiguous, STOP, leave last-good, don't improvise
on production"), I stopped rather than restart prod, write to the protected cluster, or
improvise the poll architecture.

---

## Per-host state

### OCI (this box) — live, **old code**, role unset
- Now: native `infradocs-v6-api.service` active since 2026-06-24 on stale code (federation/AI/
  setup routes 404). Repo working tree on `feature/federation-ui-and-dispatch`, clean; `main`
  merged + pushed. No federation timer installed (the earlier premature reap timer stays
  removed; role is still unset, correctly).
- Remains: redeploy onto `main` + **restart the API** (operator), set role=primary, mint
  tokens, install the reap timer. See checklist.

### OCI-P (100.70.18.9) — production, **pre-staged only**
- Read-only inspection: Docker 29.6.1 (no sudo), 24 G free, ports 8090/8081/8443/27018 all
  **free**, no prior V6 checkout. Protected assets present and untouched: `/data/mxh`,
  `mhx.mdbdemo.in` cert, mongo `:27017`.
- **Live change made:** cloned the repo (branch `main`, `02355d0`) to
  **`~/infradocs-v6-deploy`** (HOME, since `~/projects` is root-owned). **Nothing started** —
  verified no infradocs containers running.
- Remains: full stand-up + secondary config + poll timer — operator runs
  `deploy/OCI-P_MORNING_DEPLOY.md` (after the OCI prereq).

### N150 (100.72.146.5, ssh `manishkumarsinha@`) — **untouched**
- Read-only inspection: reachable; Docker 29.6.1 (no sudo), 387 G free, ports
  8090/8081/8443/27018 **free**; only legacy `~/projects/InfraDocs_V5` present (no V6); stale
  V5 `infradocs-scanner.timer` (inactive) left untouched.
- **No change made.** Not deployed, because (a) it would push to OCI's 404 ingest (useless
  until OCI is updated) and (b) the poll-timer architecture gap is unresolved. Standing up a
  half-functional stack on a third-party box overnight isn't a clean state.
- Remains: deploy V6 docker product alongside V5 (do not touch Nextcloud/Immich/AdGuard/V5
  timer), configure as secondary, install poll timer (same architecture decision as OCI-P).
  The OCI-P runbook is directly reusable (swap `SERVER_ID=n150`, ssh user `manishkumarsinha`).

---

## OPERATOR MORNING CHECKLIST

1. **Bring the OCI primary onto current code** (the gating step; restarts production):
   `git pull main` → `npm run build` (rebuilds the live dist) → `sudo systemctl restart
   infradocs-v6-api.service` → confirm `…/api/federation/servers` is **not** 404. Then set OCI
   `role=primary`. (Details: top of `deploy/OCI-P_MORNING_DEPLOY.md`.)
2. **Install the OCI reap timer** (now that role=primary):
   `sudo cp deploy/systemd/infradocs-fed-reap.{service,timer} /etc/systemd/system/ &&
   sudo systemctl daemon-reload && sudo systemctl enable --now infradocs-fed-reap.timer` →
   verify `systemctl list-timers | grep infradocs-fed`.
3. **Decide the poll-on-docker architecture** (Option A docker-exec vs B host venv in the
   runbook), then **commit the chosen poll unit** back to `deploy/systemd/`.
4. **Deploy OCI-P** as secondary: follow `deploy/OCI-P_MORNING_DEPLOY.md` end-to-end; confirm
   `oci-p` appears in `…/api/federation/servers` and one poll cycle runs clean.
5. **Deploy N150** the same way (reuse the runbook; `SERVER_ID=n150`, ssh `manishkumarsinha@`).
6. **UAT:** from the Servers lens, see OCI (primary) + OCI-P + N150; dispatch a benign action
   (e.g. `restart`) to a secondary and watch it execute + audit; confirm `infradocs-v6-*` is
   refused (409); confirm reap leaves a stale command `expired`.

---

## ⚠ LIVE CHANGES MADE OVERNIGHT (nothing hidden)

| Where | Change | Reversible by |
|---|---|---|
| git `main` (origin) | Merged `feature/federation-ui-and-dispatch` (no-ff, `02355d0`) + pushed | `git revert -m1 02355d0` |
| OCI-P `~/infradocs-v6-deploy` | `git clone` of the repo (no service started) | `rm -rf ~/infradocs-v6-deploy` |

That's the complete list. **No** service was started/stopped/restarted on any host; **no**
systemd unit changed; MongoDB / MXH / nginx / Caddy / cloudflared / certs untouched everywhere;
no writes to the federation/settings collections.

## Confirmations

- **main merged + pushed:** yes — `origin/main` at `02355d0`, suite green (sole known failure).
- **End-to-end OCI↔N150 path exercised:** **NO** — could not be, and was not faked. It is
  blocked on the OCI primary running current code (forbidden restart). It becomes exercisable
  right after morning checklist steps 1 & 4.
