# InfraDocs frontend

React 19 + Vite + Tailwind + TanStack Query SPA for the InfraDocs cockpit. Theme is
**Neon-Depth** (MongoDB-green on a dark base), static — no motion.

## Dev

```bash
npm install
npm run dev          # → http://localhost:5173, proxies /api/* to http://127.0.0.1:8004
```

The API must be running (see the repo root `README.md` / `docs/DEVELOPMENT.md`). Auth flow:
the app gate in `src/App.jsx` walks login → forced password change → setup wizard → cockpit;
the session token lives in `localStorage` as `ifd_token` and is sent as `Authorization:
Bearer`. A 401 dispatches `ifd-unauthorized` and drops the token.

## ⚠️ Building — do NOT clobber the live dist

The live OCI box serves `frontend/dist/` directly via nginx, so a bare `npm run build` /
`npx vite build` **instantly changes production**. To only verify compilation, build to a
throwaway dir:

```bash
npx vite build --outDir /tmp/ifd-check
```

Build to `dist/` **only** when you actually intend to publish.

## Layout

```
src/
├── App.jsx                 # AuthGate: login → change-pw → setup → cockpit
├── api/client.js           # axios + Bearer token + endpoint map
├── pages/
│   ├── Login.jsx · Setup.jsx        # auth + first-run wizard (incl. AI labeling)
│   ├── LensHome.jsx                 # lens nav: Dashboard/Projects/Servers/Web/Resources/Assets
│   ├── Applications.jsx · ApplicationDetail.jsx   # master-detail + topology lane
│   └── …                            # Ports, Storage, Actions, Assets, Scans
├── components/             # AppCard, ActionButton, ActionBar, StatePill, UsageBar, …
└── registry/cards.js       # CARD_REGISTRY — per-category icon/label/shape/fields/actions
```

Notable lenses: **Web** lists every reachable UI/service across the fleet (`/api/endpoints`);
the AI controls (label unknowns / fleet insights) call `/api/ai/*`. The `ServersLens` is
currently a mock pending wiring to `/api/federation/servers`.
