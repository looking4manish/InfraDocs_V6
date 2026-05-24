# Phase 9A — Frontend extension (UI for ports, storage, actions, application detail): STATUS

**Status:** Complete (awaiting user UI review with screenshots)
**Date:** 2026-05-24
**Build:** 144 modules, 13.14 KB CSS, 365 KB JS (110 KB gzipped), 813 ms

## Scope

Surface the Phase 5/7/8 data through the frontend. Phase 4 shipped 4
pages (Dashboard, Projects, Assets, Scans). Phase 9A adds Applications,
Ports, Storage, Actions, plus a rich Application Detail view with
operational action buttons.

Out of scope: visual redesign (palette / typography stay as Phase 4),
automated frontend tests, the dev-server retirement, build.sh.

## New routes

| Route | Page | Source |
|---|---|---|
| `/applications` | `Applications.jsx` | `GET /api/applications/list` (Phase 5) |
| `/applications/:name` | `ApplicationDetail.jsx` | `GET /api/applications/{name}` + cross-fetches `/api/ports/?project=` and `/api/storage/?project=` |
| `/ports` | `Ports.jsx` | `GET /api/ports/`, `/summary`, `/probe` (Phase 7B) |
| `/storage` | `Storage.jsx` | `GET /api/storage/`, `/summary` (Phase 7C) |
| `/actions` | `Actions.jsx` | `GET /api/actions/`, `/allowed` (Phase 8) |

Existing pages (Dashboard, Projects, ProjectDetail, Assets, Scans) preserved.

## Reorganized sidebar

| Section | Items |
|---|---|
| Overview | Dashboard |
| Inventory | Applications, Projects, Ports, Storage, All Assets |
| Activity | Scans, Actions Log |
| By Category | (quick filters into `/assets?category=…` for each scanner output) |

Live counts shown next to Applications / Ports / Storage / each category — driven by the summary endpoints with React Query so they refresh with the data.

## New shared components

| File | Purpose |
|---|---|
| `components/AppCard.jsx` | Application list card: name, type pill, exposure badge, component / port / disk stats, icon row for containers/systemd/nginx/volumes/images. |
| `components/ActionButton.jsx` | One-shot action button with built-in confirm() for mutating actions, output modal showing stdout/stderr/rc/ms, error handling, disabled state with tooltip for self-protected units. |
| `components/StatePill.jsx` | Color-coded pill for any state token (active/running/in_use → green, declared/queued → amber, failed/refused → rose, else slate). |
| `components/UsageBar.jsx` | Horizontal usage bar for mount % (green/amber/rose at 75/90 thresholds). |
| `components/Bytes.jsx` | `formatBytes(n)` helper used everywhere disk/volume sizes appear. |

## Application Detail — what it surfaces

For each application document:

- **Header**: name + type pill (project/system) + exposure pill (live / via Cloudflare) + "Restart app" button (fans out via `POST /api/applications/{name}/action`).
- **Top stats**: components, containers, systemd units, nginx sites, total disk.
- **URLs** (if any): clickable external links.
- **Containers**: row per container with state pill, port mapping summary, per-action buttons (logs / restart / stop / start). Self-protected containers (`infradocs-v6-*`) have buttons disabled with tooltip explaining why.
- **Compose file** path.
- **Systemd units**: row per unit with state pill + per-action buttons (status / logs / restart).
- **Nginx sites** list.
- **Docker volumes**: name, mountpoint, du size.
- **Ports** (from registry, filtered to owner): port/proto, state pill, process. Links out to full registry view.
- **Storage** (from registry, filtered to owner): kind tag, path, size. Links out to full registry view.
- **Env keys** (names only — no values, per Phase 5 design).
- **Project directory**: path + tree size + total incl. volumes.

The action result modal shows stdout/stderr with monospace formatting; for `logs` and `status` text wraps for readability.

## Ports page

- 5 stat cards: total / in_use / declared / top 2 owners by count.
- **Live probe widget**: range input (default 8000-8050) + protocol toggle + button → hits `GET /api/ports/probe`, renders all ports in the range as a heat strip (green = listening, slate = free). Not persisted; hover shows local_address.
- Filters bar (URL-synced): state dropdown, project dropdown (auto-populated from summary), port_min/port_max range inputs.
- Registry table: port/proto, state pill, owner (clickable → application detail), process, evidence badges (one chip per source: listening / container / nginx_upstream / nginx_listen / systemd_exec).

## Storage page

- 5 stat cards: total entities, total bytes tracked, top 3 kinds with count + bytes.
- **Storage by owner** visual: horizontal bar chart per owner showing share of total, with bytes + percentage. Each owner clickable → application detail.
- Kind filter tabs (All / Mounts / Docker volumes / Project trees / Bind mounts).
- Project filter pill (set by clicking an owner in the bar chart or in the table).
- Registry table: kind tag, name+path, owner (clickable), size (with total_bytes context for mounts), and usage bar for mounts / fstype label for others.

## Actions page

- Filters bar: action dropdown (from `/api/actions/allowed`), actor input, asset_id input, limit dropdown.
- Table polls every 5s.
- Each row collapses; click to expand → shows full stdout (in `<details>` with virtualized max-height), stderr (rose-tinted), and the asset_id + args JSON.
- Refused rows surface `refused_reason` (self_protect / not_allowed) as a rose-tinted column.

## Dashboard refresh

Old hero: 4 generic stat cards. New hero: 6 click-through cards covering Applications / Internet-exposed / Total assets / Ports / Storage / Last scan — each drills into the matching page.

Body adds:
- **Applications panel** (2/3 width): clickable list with type pill, exposure pill, component count, disk size.
- **Recent actions panel** (1/3 width): live audit feed, polls every 5s.
- **Asset categories** strip at the bottom (kept from Phase 4 but de-emphasized — sub-headline instead of headline).

## Bug caught + fixed during sanity testing

Phase 4's `/assets` route returned 301 → /assets/ → 403 in production because Vite's default `build.assetsDir = "assets"` literally created a `dist/assets/` directory that shadowed the SPA route. nginx served the real directory before the `try_files $uri /index.html` fallback could redirect to the SPA.

Fix in `frontend/vite.config.js`: `build.assetsDir = "static"` so bundles live under `dist/static/` instead. `/assets` is now free for the SPA. Confirmed live: `/assets → 200`.

This bug has been present since Phase 6 went live; my testing surfaced it. Old browser sessions with cached HTML may briefly 404 on the old `/assets/index-*.js` bundle name; one hard reload fixes them.

## Safety model for action buttons

- **Read-only actions** (`logs`, `status`, `test`) fire immediately, open the output modal on success.
- **Mutating actions** (`start`, `stop`, `restart`, `up`, `down`, `reload`) prompt via `window.confirm("Run \"X\"? This will affect the live host. Continue?")` before firing.
- **Self-protect**: containers/services with names starting `infradocs-v6-` have the button visibly disabled with a tooltip — the API would 409 anyway, but we tell the user up front.
- 401 responses (auth expired) wipe `ifd_pass` from localStorage so the next request triggers the browser's native auth dialog (set up post-Phase-8).

## Sanity test results (live OCI)

All 10 SPA routes return 200. All 14 API endpoints (incl. probe, filters, summary) return 200. End-to-end test:

```
container asset_id: oci:container:633839b91762 (openwebui)
logs action: success, 3 lines, 11ms
audit log shows: logs by msinha on openwebui -> success
self-protect: POST /api/assets/<infradocs-v6-api.service>/action -> 409 (expected)
```

## To activate (already done as part of this work)

No restart needed — `nginx` serves `frontend/dist/` directly. `npm run build` regenerated the bundle; nginx picks it up on next request. The browser may need a hard reload if it cached the old `/assets/*` bundle paths (see "Bug caught" above).

## Open items (Phase 9B+)

- Frontend automated tests (Vitest + Testing Library).
- Retire the leftover Vite dev server on `:5173` — visible in the ports registry as an unowned `5173/tcp listening`.
- `deploy/build.sh` that runs `npm run build` + (optionally) reloads nginx.
- Tighter typography / icon set / inline charts (small sparklines on disk usage, etc.) — pending screenshot-driven feedback via [`UI_REFINEMENT_PROMPT.md`](../UI_REFINEMENT_PROMPT.md).
- Search bar in Header currently does nothing — wire it to a global asset/app search.
