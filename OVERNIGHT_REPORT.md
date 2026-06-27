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
