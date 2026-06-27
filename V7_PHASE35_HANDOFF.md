# InfraDocs V7 — Session Handoff (2026-06-14) — Wave B, UI fixes, running-flag fix, multi-server next

> 🗄️ **HISTORICAL (as of 2026-06-27).** Point-in-time session record, kept for the journal.
> Its branch/commit/push notes are stale — all work is now on `main` (`feature/neon-depth-theme`
> is in sync with `origin/main`). For current state read [`CONTEXT.md`](CONTEXT.md).

> Companion to `V7_PLAN.md`, `REGISTRY_SPEC.md`, and the prior handoffs. Carries the truth from the
> session that **fixed the running-flag contract bug**, **shipped Wave B safe-subset actions**, and
> **closed every in-repo frontend item**. The next big phase — **multi-server push agent (Model A)** —
> is designed but NOT started.
>
> To resume: attach `V7_PLAN.md` + `REGISTRY_SPEC.md` + this file and say:
> *"Resume InfraDocs V7. Build the multi-server push agent (Model A, §3). C.H.A.I.N. protocol."*
>
> - **Repo:** `/home/msinha/projects/InfraDocs_V6` (OCI, user `msinha`)
> - **Branch:** `feature/frontend-cockpit` @ `34dd4af` — **AHEAD of origin by several commits, NOT pushed**
> - **Live:** https://infra.ocialwaysfree.site (nginx serves `frontend/dist`, proxies `/api/`→`:8004`)
> - **API:** systemd unit **`infradocs-v6-api.service`** (this is the deploy owner; restart via
>   `sudo systemctl restart infradocs-v6-api.service`). Bare uvicorn `app.api.main:app` on `127.0.0.1:8004`.
> - **Build/deploy:** `cd frontend && npx vite build` → served immediately (no restart). Backend changes
>   need an API restart to load.
> - **Auth:** Basic, user `msinha`. **CREDENTIAL EXPOSED IN CHAT — ROTATE (see §5).**
> - **Protocol:** C.H.A.I.N. — one action/turn, State Block every turn, backups before overwrite,
>   `venv/bin/python` for pytest, terse, autonomous decisions (Operator does UAT at the end, not per-step).

---

## 0. IMPORTANT TOOLING NOTE (saves a lot of failed turns)

Several source files on disk are **double-newline-spaced** (`\n\n` between every line) — an artifact of
prior heredoc edits. **Multi-line string anchors in Python patch scripts WILL miss** against these files.
Use **single-line anchors** or **single-token replacements** (`<motion.button`, `</motion.div>`, one
unique line at a time). All patch scripts validate in `/tmp` + esbuild/py_compile before writing; keep
that discipline. JSX validate: `npx esbuild FILE --loader:.jsx=jsx --bundle --external:react ... --format=esm`
(multi-file needs `--outdir`; validate one file per invocation instead).

---

## 1. THE RUNNING-FLAG BUG — FIXED (code), needs only a live rescan-confirm

**Status: RESOLVED at code level. Committed `2a93e20` (amended `65aee41`).** Verified end-to-end this
session: running the real docker scanner + correlator in-process returns
`CORRELATOR containers_detail running = [('openwebui', True)]` and the union read `UNION = True`.

**What it was:** live docker scanner writes running truth to the **asset top level**
(`health_indicators.running` + `status=="running"`), never to `metadata.running`. The correlator read
`bool(meta.get("running"))` only → live containers always `running:False`, wrongly flagged in
`hygiene.exited_restart_always`. openwebui showed `exited` while `Up 8 days (healthy)`.

**The fix (in `app/correlator.py`, Pass 2 ~line 191):** derive once per loop
```python
running = bool(
    meta.get("running")
    or (c.get("health_indicators") or {}).get("running")
    or c.get("status") == "running"
)
```
applied at both the `containers_detail` append and the hygiene guard. Test guard added in
`tests/test_v7_phase1_correlator.py`: `_asset()` gained a `status=` kwarg +
`test_live_shape_running_via_health_indicators` (live shape: running via health_indicators+status, no
metadata.running). **18/18 green.**

**Why live still showed False mid-session:** the API process predated the loaded fix at the moment of an
earlier rescan; the code is correct. **Next session: one rescan on the current process + verify**
(`POST /api/scans/trigger`, wait ~10s, GET `/api/applications/openwebui` → expect `running: True`,
`hygiene.exited_restart_always` empty). No code change expected.

---

## 2. What shipped this session (all committed on `feature/frontend-cockpit`)

Commit order: `2a93e20`/`65aee41` (correlator) → `f2b25f2` (Wave B) → `816a3cf` (modal portal + back-nav)
→ `c20aa44` (last-action chip) → `0c82abf` (project-card actions) → `34dd4af` (drop Resources lens).

### 2a. Wave B actions — safe subset ✓ (`f2b25f2`)
`app/actions.py` + `frontend/src/registry/cards.js` + `tests/test_phase8_actions.py`. **28/28 green.**
Live `/api/actions/allowed` confirmed. Added:
- **docker_compose** `recreate` (= `up -d --force-recreate`), destructive.
- **systemd_timer** `trigger` (= `systemctl start <unit>.service`, strips `.timer`), self-protected.
- **docker_image** `prune` (`docker image prune -f`), destructive.
- **NEW category `docker_volume`** {`inspect`, `prune`} — handler `_act_docker_volume`.
- **NEW category `storage_mount`** {`inspect`} (`findmnt -T <mountpoint> --output …`) — handler `_act_storage_mount`.
- cards.js ACTION_META gained `prune`/`recreate`/`trigger` (icons Trash2/RefreshCcw/PlayCircle);
  docker_volume now an `entity` shape with actions.
- **DEFERRED on purpose:** `network_port identify/kill` — arbitrary-PID-by-port is too risky to ship as
  default; revisit behind extra confirmation + self-protect on port 8004 / the API's own PID.

### 2b. Action-output modal portaled to body ✓ (`816a3cf`)
`frontend/src/components/ActionButton.jsx`: `ActionOutputModal` now `createPortal(..., document.body)`
at `z-[80]`. Fixes nginx `test`/`reload` (and logs/status/inspect/stats) output being trapped + clipped
**behind** topology-lane flow nodes (the lane's `overflow` clipped the previously-non-portaled modal).
UAT-confirmed by Operator.

### 2c. Detail back-link → LensHome cards ✓ (`816a3cf`)
`frontend/src/pages/ApplicationDetail.jsx`: `← All applications` link changed `/applications` → `/`
so returning from a project lands on the **card** view (LensHome), not the flat Applications list.
UAT-confirmed.

### 2d. Last-action status chip ✓ (`c20aa44`)
NEW `frontend/src/components/LastActionChip.jsx` + mounted in `ActionBar.jsx`. Reads
`/api/actions/?asset_id=&limit=1`, renders compact `verb + relative-time` chip (emerald=success,
rose=failed/refused, tooltip = actor+status). Frontend-only; audit log already had everything
(`record_action`/`get_actions` in `app/core/db_manager.py`, `actions_log` collection, `timestamp` DESC).

### 2e. Project-card app-level actions ✓ (`0c82abf`)
`frontend/src/pages/LensHome.jsx`: `ProjectLensCard` root changed `motion.button` → `motion.div` with a
full-card nav-button underlay (`absolute inset-0 z-0`) + content `pointer-events-none` passthrough so the
whole card still navigates. NEW `AppActionRow` overlay (bottom-right, hover-revealed, click-isolated via
`stopPropagation`) fires `endpoints.fireApplicationAction(name, verb)` for restart/up/down. A wrapper
flattens the multi-target `{results:[…]}` response into modal-friendly stdout text.

### 2f. Resources lens dropped ✓ (`34dd4af`)
`LensHome.jsx`: removed redundant `"Resources"` lens (it duplicated `<Dashboard/>`; the Assets lens
already covers registry drill-down). Lenses now: **Dashboard · Projects · Servers · Assets.**

---

## 3. THE NEXT BIG PHASE — Multi-server push agent (Model A) — NOT STARTED

**Decision locked with Operator: Model A (push agent), not central remote-scan.** Rationale: N150 is behind
CGNAT (must push outbound), Tailscale is everywhere, `app/agent.py` + `server_id` plumbing already exists.
Goal: InfraDocs must be **deployable / run remotely to collect the same data from other servers**
(OCI-P `100.70.18.9`, N150 `100.72.146.5`, OMEN `100.98.102.10`) into one shared store + UI. The Servers
lens already shows OCI live + OCI-P/N150/OMEN as **dashed "pending-agent"** — this phase activates them.

**Build outline (each step = registry/handler/endpoint + test, C.H.A.I.N.):**
1. **Ingest endpoint** — `POST /api/ingest` (or `/api/assets/bulk`): accepts `{server_id, assets[],
   scanned_at}` from a remote agent, authenticates (per-agent token, NOT the msinha basic cred),
   upserts assets tagged with that `server_id`, runs correlation **scoped to that server_id**, writes
   per-server applications. Must not clobber other servers' assets (scope deletes/replaces by server_id).
2. **Agent packaging** — a slim runnable (reuse `app/agent.py` + `app/scanners/*`) that runs ON each
   target, scans locally, POSTs to the central ingest URL over Tailscale. Config: central URL, server_id,
   agent token. Ship as a systemd unit + timer (periodic push) per server.
3. **Per-server correlation** — `correlate()` is already `server_id`-parameterized; ensure the store +
   API filter/group by server_id end-to-end (assets, applications, the Servers lens).
4. **Servers lens activation** — turn the dashed pending hosts live once their agent reports; show
   last-push time + per-server health.
5. **Auth model** — per-agent bearer tokens (issue/store/verify); keep agent creds out of chat.

**Watch-outs:** correlation currently runs on the *trigger* host's local scan (`scans.py` `_run_scan_job`
loops local SCANNERS). The ingest path must run correlation on the *pushed* asset set for that server_id
WITHOUT running local scanners. Don't let an ingest for OCI-P wipe OCI's assets — scope every
replace/delete by server_id.

---

## 4. Remaining smaller bugs (deferred, after multi-server or interleaved)

- **`ssl_not_after` / `ssl_issuer` null** — nginx cert parse perms (known carryover; `msinha` likely
  can't read the cert/key under `/etc/letsencrypt`). Either grant read via group/sudo helper or parse
  the cert out-of-band.
- **systemd timer units not in `deploy/`** — the `infradocs-v6-*` unit files aren't tracked under
  `deploy/`; add them so the deploy is reproducible (relevant to the multi-server agent packaging too).
- **vite >500 kB chunk warning** — Phase 5 lazy-route/code-split fixes it; cosmetic for now.
- **Double-newline-spaced source files** — cosmetic; normalize opportunistically (see §0). Do NOT mass-
  reformat in a feature commit.

---

## 5. CLOSEOUT TASKS (do these to finish cleanly)

- **PUSH the branch** — `feature/frontend-cockpit` is ahead of origin by ~6 commits this session and was
  never pushed. `git push origin feature/frontend-cockpit` (confirm remote first).
- **ROTATE the `msinha` API credential** — pasted in plaintext multiple times this session
  (`Changeme001`). Auth is Basic over localhost/Tailscale; rotate when convenient. This matters more once
  the multi-server agent exists (don't reuse this cred for agents — use per-agent tokens).
- **Housekeeping deletions** — ~20 `dist.bak.2026052*/` directory deletions still sit **unstaged** in the
  working tree (pre-existing, unrelated to this session). Either a lone housekeeping commit or
  `git checkout -- ` to drop. Deliberately excluded from every session commit so far.
- **Operator UAT pass (end-to-end)** — Operator deferred per-step UAT. Verify: Wave B actions on real
  assets (recreate/trigger/prune/volume+storage inspect), last-action chips updating, project-card
  up/restart/down firing + modal summary, back-nav lands on cards, and the running-flag rescan (§1).

---

## 6. Backups created this session (gitignored via `*.bak.v7-*`)
`app/correlator.py.bak.v7-10run` · `tests/test_v7_phase1_correlator.py.bak.v7-10run/.v7-10sp` ·
`app/actions.py.bak.v7-waveB` · `frontend/src/registry/cards.js.bak.v7-waveB` ·
`tests/test_phase8_actions.py.bak.v7-waveB` · `ActionButton.jsx.bak.v7-portal/.v7-portal2` ·
`LensHome.jsx.bak.v7-appbar` · `ActionBar.jsx.bak.v7-chip`.

## 7. Verified ground truth (don't re-derive)
- Live openwebui container asset: `oci:container:92d9329a9504`, top-level `status:"running"`,
  `health_indicators={running:true, restarts:0, has_health_check:true, health_status:"healthy"}`,
  `metadata.running` ABSENT. Container is `Up`/healthy — never a service outage.
- Action log: `app/core/db_manager.py` `record_action`/`get_actions`, collection `actions_log`,
  fields incl. `asset_id, asset_name, category, action, status, return_code, duration_ms, refused_reason,
  actor, timestamp`. Indexed: `timestamp` DESC, `asset_id`, `action`.
- client.js endpoints: `allowedActions`, `listActions({asset_id,action,actor,limit})`,
  `fireAssetAction(assetId,action,args)`, `fireApplicationAction(name,action,args)`,
  `listAssets({category})`, `listApplications()`.
- Routes (`App.jsx`): `/` LensHome · `/dashboard` · `/applications` (flat list) ·
  `/applications/:name` ApplicationPanel · `/projects` · `/projects/:name` · `/assets` · `/ports` ·
  `/storage` · `/actions` · `/scans`. AppShell sidebar already removed.
- Scan pipeline: `app/api/routers/scans.py` `_run_scan_job` runs local SCANNERS, upserts each asset,
  then `correlate(all_assets, server_id=cfg.server.id, projects_root=…)` → `replace_applications`.
- Build always clean except the pre-existing >500 kB chunk warning.