# InfraDocs — Session Handoff (2026-06-23) — Neon theme · IA pass · image-update flow

> 🗄️ **HISTORICAL (as of 2026-06-27).** Point-in-time session record, kept for the journal.
> The work is on `main`. For current state read [`CONTEXT_FOR_LLM.md`](CONTEXT_FOR_LLM.md) and
> [`CONTEXT.md`](CONTEXT.md).

> Branch **`feature/neon-depth-theme`** (pushed to origin). Three deliverables this
> session, all committed + verified. **Nothing is deployed to prod yet** — see Deploy.
> Repo `/home/msinha/projects/InfraDocs_V6` (OCI, user `msinha`).

## LATEST (end of 2026-06-23) — visible restructure + the cache fix
- `52d245f` — **Master-detail split-pane for Applications** (the visible restructure):
  list left / live detail right, selection in `?sel=` (list never remounts),
  responsive stack on mobile, `/applications/<name>` redirects into `?sel=`.
  DEPLOYED (frontend build) + verified in the live bundle.
- `6ba8177` — **nginx cache fix (NOT applied — needs you)**. Found the real reason
  "I don't see changes": `index.html` was served with **no Cache-Control**, so the
  browser cached the old entrypoint → old bundle. Fixed in
  `deploy/infra.ocialwaysfree.site.conf` (no-cache on index.html; immutable on the
  real `/static/` path). The auto-mode guard blocked me from touching live nginx.
  **Apply it (e.g. during the morning restart):**
  ```
  sudo cp deploy/infra.ocialwaysfree.site.conf /etc/nginx/sites-available/infra.ocialwaysfree.site
  sudo nginx -t && sudo systemctl reload nginx
  ```
  Until applied, **hard-refresh (Ctrl/Cmd+Shift+R) or use Incognito** to see today's work.

## What shipped (commits, oldest→newest)
- `075a7cf … 3c8d182` — **MXH Neon-Depth theme** (tokens + global depth CSS + shared
  components + page sweep). MongoDB-green #00ED64 signal, slate-navy canvas, strain
  ramp. STATIC only — TopologyLane comet + skeleton-shimmer keyframes untouched.
- `ca11597` — **IA pass (entity-centric nav)**: URL-addressable lenses (`?lens=`),
  deep-linkable drawer (`?d=app:|asset:`, Back closes), AssetRow opens the universal
  drawer (table no longer a dead end), Breadcrumbs on Application/Project detail,
  retired duplicate `/dashboard` route, deleted dead `Sidebar.jsx`.
- `365eb47` — **Backend image-update flow**: `docker_compose` **`update`** (= compose
  pull + up -d; aborts if pull fails) and `docker_image`/`docker_container`
  **`check_update`** (read-only: compares local RepoDigest vs registry manifest digest
  via docker SDK; `details.update_available` = true|false|null). Docker scanner now
  captures image `repo_digests`. 35 action+API tests green.
- `c6d0142` — **Dynamic action buttons in the drawer**: ActionBar mounted in the
  drawer (AssetBody + container rows). `update` (primary on compose), `check_update`
  (primary on image). The drawer is now the operable surface.

## Verification done
- `venv/bin/python -m pytest tests/` → all green except a pre-existing stale snapshot
  I fixed (`test_phase8_api::test_list_allowed` → resilient superset check).
- `npx vite build` → green (pre-existing >500 kB chunk warning only).
- eslint clean on changed files except one **pre-existing** `useDrawer`
  fast-refresh export warning in DrawerProvider (harmless; dev HMR only).
- No browser-driver installed → interaction testing was NOT automated. Dev server on
  `:5173` (HMR) is the visual UAT surface.

## DEPLOY (not done — operator/explicit auth required)
Prod currently serves the **Neon theme only** (from an earlier `dist` build); the IA +
drawer + update buttons are **committed but not live**. The action buttons need the
backend live to dispatch. Auto-restart was blocked by the deploy guardrail — run:
```
# 1. activate backend (new actions) — ~2s downtime
sudo -n systemctl restart infradocs-v6-api.service
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8004/api/health   # expect 200
# 2. activate frontend (theme + IA + drawer) — instant, nginx serves dist
cd frontend && npx vite build
```
Restart first so the UI is never ahead of the backend. To preview without going live:
`cd frontend && npx vite build --outDir dist_preview`.

## How the update flow works (operator mental model)
- Open an app → container/compose/image opens in the drawer with type-appropriate buttons.
- **Image / container → “Check update”** (read-only): tells you if a newer image exists.
- **Compose → “Update”** (confirm-gated): pulls newer images + recreates. This is the
  real upgrade; `recreate` alone never pulls.

## What's next (backlog, priority order)
1. **App-level Update button** (one click on the project card). Today `update` lives on
   the compose entity; app-level fan-out (`/applications/{name}/action`) targets
   containers+units only, so app-level up/down/update are currently no-ops. Extend the
   fan-out to resolve the docker_compose asset (watch: don't double-restart). Add tests.
2. **Passive “update available” badge** — persist `check_update` results (or a periodic
   scan pass) so the card shows a badge without clicking. Needs a store write + UI.
3. **Frontend test harness** (vitest + testing-library or Playwright) — we hit the
   can't-browser-test wall; stand this up so UI changes are verified, not eyeballed.
4. **Multi-server push agent (Model A)** — `/api/ingest`, agent on N150/OMEN/OCI-P over
   Tailscale, per-server correlation, Servers lens goes live. (THE next big phase.)
5. Scanner wave (db/rs0, exposure, backup, cron, tailscale, cloudflare, git, certs,
   host facts, OCI substrate) · Map page (React Flow, also fixes the chunk warning) ·
   diff engine → Changes feed · heal engine (dry-run).
6. Housekeeping: rotate the `msinha` API credential (exposed previously) · the ~20
   `dist.bak.2026052*/` deletions + V7_PHASE35_HANDOFF.md edit still sit unstaged ·
   ssl cert-parse perms · infradocs units not tracked in `deploy/`.

## Deferred IA items (need visual UAT / backend)
Topology nodes → drawer · master-detail split-pane on desktop · real Server page ·
generalize the lane to entity-composition + non-routing edges (needs V7 `links[]`).
