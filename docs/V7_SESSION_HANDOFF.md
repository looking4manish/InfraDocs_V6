# InfraDocs V7 — Session Handoff (2026-06-11)

> Companion to `V7_PLAN.md` (the strategy doc). This file carries the **implementation truth and
> lessons** from the session that shipped Phases 1 + 2, so the next session starts with zero
> re-discovery. Attach BOTH files when resuming: *"Resume InfraDocs V7 at Phase 3. C.H.A.I.N."*

---

## 1. What shipped this session

### Phase 1 — Correlator v2 + heartbeat ✓
- `app/correlator.py` rewritten (V6 original at `app/correlator.py.bak.v6`). Additive fields on
  every application doc: `links[]`, `containers_detail[]`, `nginx_detail[]`, `hygiene{}`,
  `resilience{}`. All legacy fields/shapes untouched.
- `tests/test_v7_phase1_correlator.py` — 17 new tests. Full suite: **29/29 green** including the
  live-scan integration test.
- Heartbeat: `/etc/systemd/system/infradocs-v6-agent.{service,timer}` — oneshot agent run every
  6h (`OnUnitActiveSec=6h`, `Persistent=true`), User=msinha, EnvironmentFile=REPO/.env,
  ExecStart=`venv/bin/python -m app.agent scan`. Enabled and verified.
  **NOT yet copied into `deploy/` in the repo — do this + commit.**

### Phase 2 — Frontend foundation ✓
New files:
- `frontend/src/lib/attention.js` — `computeAttention(apps, lastScanAt)`, `freshness()`,
  `parseScanTime()`, `normalizeList(data, keys)` (defensive shape handling).
- `frontend/src/components/DrawerProvider.jsx` — context (`useDrawer().openDrawer({type:
  "application"|"asset", name|id})`) + right slide-in drawer. Application body renders status
  pills, urls, containers_detail rows, nginx_detail rows, **link-evidence rows** (and an amber
  "No linking evidence found" state), hygiene warnings. Asset body renders metadata JSON.
- `frontend/src/components/CommandPalette.jsx` — ⌘K/Ctrl+K, fuzzy (prefix > substring >
  subsequence), groups: Navigate / Actions (trigger scan) / Applications / Assets. Selection →
  drawer or navigate. Also opens via synthetic KeyboardEvent (Header button does this).

Replaced (originals in git): `frontend/src/App.jsx` (DrawerProvider + CommandPalette mounted
inside BrowserRouter), `frontend/src/components/Header.jsx` (freshness pill `oci · Xm`,
attention chip + popover, palette trigger button, scan button kept, brand bumped to "v7").

Theme pass (applied via python patch, all in git diff):
- `tailwind.config.js` tokens: card `#0f0f12`, elev `#16161a`, hover (= border color)
  `#1c1c21`. Canvas stays pure black, accent stays violet `#8b5cf6`.
- `Dashboard.jsx` PALETTE muted: `#7c6ee6 #3aa389 #c79a4b #5b8fd0 #c4684d #9d8df1 #4fb8ab
  #c97fa6 #8fae5a #c98262`.
- `index.css` appended: thin scrollbars, violet selection, focus-visible ring, and a 24px
  dot-grid (`radial-gradient` at 3% white) on `main`.

### Bugs found & fixed
1. **Agent scan_logs were invisible.** `run_scan()`'s `insert_scan_log` dict had no
   `started_at`; the scans router sorts `started_at DESCENDING`, Mongo null-sorts missing
   fields last → every CLI/timer scan ever ran was sorted to the bottom. The visible May
   entries were API "Scan now" runs (that path writes `scan_id/started_at/finished_at`).
   Fix: `app/agent.py` patched to add `scan_id` (uuid4 hex), `started_at` (the existing
   `start` var), `finished_at`. Verified: today's scans now lead the list.
2. **openwebui container down since ~Jun 4** — `running:false`, restart=always; hygiene
   flagged it on first V7 scan; chat.ocialwaysfree.site affected. **Operator has NOT yet
   confirmed restarting it** (`cd ~/projects/openwebui && docker compose up -d`). Ask.

---

## 2. Verified ground truth (do NOT re-derive, do NOT guess beyond this)

- Python env: `REPO/venv` — always `venv/bin/python` for pytest/agent. System python3 lacks
  `docker` module.
- API: `http://localhost:8004`, Basic Auth user `msinha`; use `curl -u msinha` (interactive
  password). Frontend auth: creds in localStorage via `getCreds/setCreds` in
  `frontend/src/api/client.js`; all endpoints live in its `endpoints` object.
- Response shapes (verified live): scans → `{count, scans:[{scan_id, started_at, finished_at,
  status, total_assets, applications_built, duration_seconds, scanners:[...], ownership_audit}]}`;
  applications list → `{count, applications:[...]}`; app doc → see openwebui dump in plan +
  new V7 fields. `/api/applications/list` latency ~32ms (not a perf concern).
- Scanner metadata key names (verified by grep): container `running` (bool — there is NO
  state/health string), `restarts`, `has_health_check`, `healthcheck_defined`,
  `restart_policy` (string in practice; code handles dict), `started_at`, `host_ports`,
  `compose_service`, `compose_project`; image `is_dangling`, `in_use`, `tags`; volume
  `compose_project`, `mountpoint`, `size_bytes` + top-level `health_indicators.in_use`;
  nginx `config_file, server_names, listen, listen_ports, upstream, upstream_host,
  upstream_port, has_ssl, ssl_certificate, ssl_issuer, ssl_not_after, cloudflare_origin,
  internet_exposed, url`.
- Current live numbers: 267 assets, 8 applications (incl. new project `atlas-rag-demo`),
  Dashboard previously showed 24 ports / 48 GB / 15 storage entities.
- Frontend stack details that matter: React Router 7 nested route `/applications/:name` →
  `ApplicationPanel` (side-panel pattern already exists — Phase 3 lane goes here or replaces
  it); `motion/react` (NOT framer-motion import path); lucide-react icons; TanStack Query 5;
  recharts on Dashboard; Geist/Geist Mono fonts.

---

## 3. Process lessons (cost us real time — enforce these)

1. **Heredoc only. Cockpit editor is banned.** Two incidents: a paste never saved, and a paste
   landed in the WRONG open file — it overwrote `app/correlator.py` with test content (caught
   via circular-import traceback, recovered by re-writing via heredoc). All file transfers:
   `cat > path << 'EOF' ... EOF` pasted in the terminal. Add a verify line (`grep -c marker`,
   `py_compile`, `ls -la`) to every write command.
2. **Verify field names before coding against them** (`grep -nE '"[a-z_]+":'` on the producer)
   — this caught that containers have `running` not `state`, preventing silent empty UI.
3. **Operator sometimes runs the verify step before the write step** — make commands
   self-gating (e.g. `ls | grep x && pytest ...`) so nothing runs against missing files.
4. Backups before replacement (`.bak.v6` saved the day); originals also in git.
5. `sudo` works for systemd unit installs; mongosh is NOT usable (auth) — always go through
   the API or the venv agent.

---

## 4. Known open items (small)

- `ssl_issuer` / `ssl_not_after` come back **null** on live nginx_detail — scanner can't parse
  the cert (CF origin cert path or file perms). Attention cert rules are therefore dormant.
  Slated for the certs-registry work; harmless meanwhile.
- nginx :80 redirect blocks produce a second weaker `project_tag` link beside the
  authoritative `upstream_port:N` link for the same server_name — UI should prefer strongest
  evidence per (src_kind, src) when rendering chains.
- Vite chunk-size warning (>500 kB) — pre-existing; resolved by Phase 5's lazy React Flow route.
- Timer units not yet in `deploy/` dir; session work not yet git-committed (Operator to commit).
- Dashboard page is only token-polished, not rebuilt — by design; Phase 3's lens home replaces it.

---

## 5. Phase 3 opening (next session)

Scope: lens home (Projects | Servers | Resources | Assets tabs + ghost cards + demoted stats)
and ApplicationDetail → topology lane (url → nginx → port → container → storage with evidence
chips), per the approved mockups in plan §4.

Step 3.1 (first Operator action): from REPO —
`cat frontend/src/pages/Applications.jsx frontend/src/pages/ApplicationPanel.jsx frontend/src/components/AppCard.jsx`
— the lane must land inside the existing nested-route/panel pattern, and the lens home will
recycle AppCard if it's close enough. Then decide: rebuild `Dashboard.jsx` as the lens home
(route `/` keeps working) vs new page. Recommendation: rebuild in place.

Style contract for new Phase 3 components (match what's now live): hairline borders
`border-bg-hover`, cards `bg-bg-card rounded-2xl`, labels `text-[10px] uppercase
tracking-[0.08em] text-zinc-600`, numerals `font-mono tabular-nums`, violet for interaction
only, status colors only for state, muted PALETTE above for any charts, spring motion
(`type:"spring", stiffness ~400, damping ~36`), skeleton pulse instead of "Loading…" text.