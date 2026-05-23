# Phase 4 — Frontend: STATUS

**Status:** Code complete — **awaiting your UI-test feedback**
**Date:** 2026-05-23
**Build:** 134 modules, 8.92 KB CSS, 324 KB JS (103 KB gzipped), 779 ms

## Scope

React+Vite SPA on `:5173` consuming the Phase 3 API. Dark theme, sidebar+header layout, four pages, live counters, scan trigger.

## Where to test

Vite dev server is **already running** on this box:
- **Local:** http://localhost:5173/
- **Tailscale (from any of your devices):** http://100.107.140.36:5173/

API server is **also already running** at http://127.0.0.1:8004 and is proxied through Vite at `/api/*`.

Default creds (dev only): `msinha` / `msinha123` — hardcoded in the axios client; can be overridden via localStorage (`ifd_user`, `ifd_pass`).

## Stack

| Tool | Version | Purpose |
|---|---|---|
| React | 19.2 | UI |
| Vite | 8.0 | Dev server + build |
| React Router | 7 | Client-side routing |
| TanStack Query (React Query) | 5 | Data fetching + caching + polling |
| Tailwind CSS | 3.4 | Styling |
| axios | 1.x | HTTP client (Basic auth header) |

## Deliverables

```
frontend/
├── index.html
├── vite.config.js          # API proxy: /api/* → :8004
├── tailwind.config.js      # dark palette (bg-*, accent)
├── postcss.config.js
├── src/
│   ├── main.jsx            # QueryClient provider + root render
│   ├── App.jsx             # Routes + page layout
│   ├── index.css           # Tailwind + base
│   ├── api/
│   │   └── client.js       # axios instance + Basic auth + endpoint map
│   ├── components/
│   │   ├── Header.jsx      # logo + search + "Scan now" button
│   │   ├── Sidebar.jsx     # nav + live category counters
│   │   ├── ProjectCard.jsx
│   │   ├── AssetRow.jsx
│   │   └── HealthBadge.jsx
│   └── pages/
│       ├── Dashboard.jsx   # stat cards + project list + categories
│       ├── Projects.jsx    # grid of ProjectCards
│       ├── ProjectDetail.jsx
│       ├── Assets.jsx      # filterable table (query string sync)
│       └── Scans.jsx       # scan history + trigger button (3s polling)
```

## Pages

| Route | Page | What it shows |
|---|---|---|
| `/` | Dashboard | 4 stat cards (projects, total assets, last scan, last scan status), project list, categories list |
| `/projects` | Projects | Grid of project cards w/ health score |
| `/projects/:name` | ProjectDetail | All assets owned by the project, in a table |
| `/assets` | Assets | Filterable asset list (`category`, `project`, `status` via URL params) |
| `/scans` | Scans | Scan history table + "Run scan" button, auto-refreshing every 3s |

## What you should look at when testing

1. **Dashboard loads with real data** — should show 5 projects, ~246 assets total, last scan info.
2. **Project cards** at `/projects` — click one (e.g. `openwebui`) → assets table loads.
3. **Sidebar category counts** — the numbers next to each system-resource link should match real counts.
4. **Filtered assets** — click "Systemd Services" in the sidebar → URL becomes `/assets?category=systemd_service`, table filters.
5. **Scan trigger** — click "Run scan" (header or Scans page) → row appears in `/scans` as `running`, transitions to `success`, total assets updates.
6. **Health colors** — green ≥90, amber 70-89, red <70.
7. **Dark theme** — consistent across pages.

## Known rough edges (please flag if they bug you)

- No login form. Creds are hardcoded `msinha:msinha123` until you tell me otherwise (or set `INFRADOCS_API_PASSWORD` in `.env`).
- No favicon — browser will show a generic globe.
- No mobile breakpoint testing yet (built desktop-first).
- "Scan now" in the header shows a tiny scan_id snippet but no progress bar; the Scans page is the place to watch progress.
- Search box in the header is wired to nothing — placeholder for Phase 5/6.

## Tests

- Build: `npm run build` succeeds.
- Dev server: starts in 241 ms, HMR works.
- API proxy verified end-to-end via curl through `:5173/api/*` with basic auth.

There are no Vitest unit tests yet — frontend testing is delegated to your manual UI pass per the workflow we agreed on. I can add Vitest + RTL tests in Phase 5/6 if you want regression coverage on the components.

## Next: Phase 5 — Operational controls

Container/service start/stop/restart/logs, nginx test/reload. These will need new API endpoints (`POST /api/assets/{id}/action`) backed by subprocess calls + new UI action buttons on the asset detail view.
