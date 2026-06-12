# InfraDocs V7 — Phase 3.5 Session Handoff (2026-06-12)

> Companion to `V7_PLAN.md` (strategy), `REGISTRY_SPEC.md` (the card/action registry spec), and the
> earlier Phase 1-2 handoff. This file carries the **implementation truth** from the session that
> shipped the Phase 3 hero pages + the Phase 3.5 registry spine. To resume:
> attach `V7_PLAN.md` + `REGISTRY_SPEC.md` + this file and say:
> *"Resume InfraDocs V7 at Phase 3.5 Step 3.5.6m (motion pass). C.H.A.I.N. protocol."*
>
> - **Repo:** `/home/msinha/projects/InfraDocs_V6` (OCI, user `msinha`)
> - **Live:** https://infra.ocialwaysfree.site (nginx serves `frontend/dist` statically, proxies `/api/`→`:8004`)
> - **Build/deploy:** `cd frontend && npx vite build` → nginx serves new `dist/` immediately (no restart)
> - **Protocol:** C.H.A.I.N. — one action/turn, State Block every turn, heredoc-only writes (cockpit
>   editor BANNED), self-gating + verify on every write, backups before overwrite, `venv/bin/python`
>   for all pytest/agent, API/agent over mongosh. Operator dislikes verbose commentary — be terse.

---

## 1. THE NEXT TASK (start here) — 3.5.6m: gold-standard motion pass

Operator wants the app to feel like a high-end web product (Linear/Vercel register). Diagnosis:
structure is done, the **motion layer is missing**. Apply across EVERYTHING built this session:
lens-home cards, topology lane nodes + connectors, link-evidence rows, the action output modal,
lens-tab switching, and skeletons.

Concrete spec (target: subtle-to-medium, NOT a demo-reel):
- **Staggered entrance** — cards/nodes/rows fade+rise in (`opacity 0→1`, `y 8→0`), ~25-35ms stagger
  via `motion` with a parent `staggerChildren`. `motion/react` is already in the stack.
- **Spring hover** — replace CSS `transition` lifts with spring (`type:"spring", stiffness:400,
  damping:36` — the handoff contract). Cards lift `y:-2`, lane nodes too.
- **Layout transitions** — wrap lens-tab content in `<AnimatePresence mode="wait">` so switching
  Dashboard/Projects/Servers/etc cross-fades instead of hard-cutting. Same for the action modal
  (scale+fade in).
- **Shimmer skeletons** — replace flat `animate-pulse` blocks with a moving gradient shimmer.
- **Respect `prefers-reduced-motion`** — gate the big motions.

Suggested order (one heredoc each, build-verify between): (1) lens-home cards stagger+spring,
(2) lane nodes+connectors, (3) evidence rows + modal, (4) lens-tab AnimatePresence, (5) shimmer.
Operator will want to FEEL each surface — expect calibration ("more/less"). Don't batch all 5 blind.

After motion: resume the deferred 3.5.x items in §4.

---

## 2. What shipped this session

### Phase 3 — Hero pages ✓
- **`TopologyLane.jsx`** (NEW, ~293 lines) — derives `url→nginx→port→container→storage` from
  `nginx_detail[]`/`containers_detail[]`, renders flow nodes + evidence chips on connectors +
  `LinkEvidence` panel from `links[]`. `strongestNginx()` picks the :443 block over the weak :80
  redirect (avoids the dup null node). Mounted in `ApplicationDetail.jsx` above legacy Sections.
- **Full-width detail route** — `/applications/:name` promoted from a nested drawer child to a
  top-level route (was choking the lane at 1/3 width). `App.jsx` route moved out of `/applications`
  nest; `ApplicationPanel.jsx` slimmed to a `max-w-[1100px]` full-width wrapper; `Applications.jsx`
  drawer machinery (useOutlet/AnimatePresence/aside) removed.
- **`LensHome.jsx`** (NEW, ~212 lines) — replaces Dashboard at `/`. Lens tabs
  `Dashboard · Projects · Servers · Resources · Assets` (Dashboard is default + home). Projects lens
  = AppCards from applications endpoint filtered `type:project`, attention-sorted. Servers lens =
  HOSTS grouped (OCI live; OCI-P/N150/OMEN dashed pending-agent). Dashboard/Resources lenses render
  the existing `<Dashboard/>` charts. **Sidebar removed** from `AppShell` in `App.jsx`.
  `/dashboard` kept as a deep-link route.

### Phase 3.5 — Card & Action Registry spine ✓
- **Backend `app/actions.py`**: `ALLOWED_ACTIONS` promoted to `ACTION_REGISTRY` (allowed +
  destructive + self_protect per category); `ALLOWED_ACTIONS`/`DESTRUCTIVE_ACTIONS` derived from it
  (back-compat). **Self-protect centralized into `dispatch()`** — now covers ALL categories, not
  just systemd (was a real gap: an `infradocs-v6-*` container wasn't protected at the executor).
  **Wave A actions added**: container `inspect`/`stats`, systemd `enable`/`disable`, new
  `docker_image` category + `pull`. `_act_docker_image` handler added + wired into `_DISPATCH`.
- **`/api/actions/allowed`** extended additively to return `destructive` map alongside `allowed`.
- **Frontend registry**: `frontend/src/registry/cards.js` (NEW) — `CARD_REGISTRY` (category→icon,
  label, shape, fields, actions) + `ACTION_META` (action→label+lucide icon) + `actionsFor()`/
  `isDestructive()` helpers. Pure data. Presentation only; backend owns permission.
- **`useAllowedActions()`** hook (`frontend/src/hooks/`) — caches `/api/actions/allowed`.
- **`ActionBar.jsx`** (NEW) — the shared action surface. Intersects registry actions × backend-allowed,
  primary inline + `⋯` overflow, destructive flagged from live map, fires via existing `ActionButton`.
  Resolves asset_id by name (`resolveByName`) since the lane only knows container names.
  Overflow menu is **portaled to body** (escapes the lane's `overflow-x-auto` clip).
- **`ActionButton.jsx`** — ICONS extended for Wave A verbs (inspect/stats/enable/disable/pull) +
  per-action icons + Loader2 spinner (done earlier this session).
- **Mounted**: ActionBar on the lane CONTAINER node — Logs inline + Inspect/Stats/Restart/Stop/Start
  in overflow. Verified firing end-to-end (Inspect + Stats return real JSON in the modal).

### Bugs fixed this session
1. React error #310 (blank page) — ActionBar had `useQuery` AFTER early `return null` (hooks rule
   violation). Fixed by hoisting ALL hooks above the returns.
2. Overflow menu clipped by lane's `overflow-x-auto` — fixed via `createPortal` to body +
   `getBoundingClientRect` positioning.
3. (earlier) Full-width lane — the drawer frame, not the lane, was the constraint.

---

## 3. Verified ground truth (do NOT re-derive)

- **Container asset_id format**: `oci:container:{12-hex}` e.g. `oci:container:92d9329a9504`.
  Containers: carp-qdrant, openwebui, atlas-rag-demo-frontend-1, atlas-rag-demo-backend-1.
- **Live action surface** (`/api/actions/allowed`): docker_container {start,stop,restart,logs,
  inspect,stats} · docker_compose {up,down,restart} · systemd_service {start,stop,restart,logs,
  status,enable,disable} · systemd_timer {…,enable,disable} · nginx_server_block {test,reload} ·
  docker_image {pull}. Destructive: stop/restart/down/disable/reload (image pull none).
- **Fire endpoints**: `POST /api/assets/{asset_id}/action` body `{action,args}` ·
  `POST /api/applications/{name}/action`. `inspect` fires `success` even on a DOWN container.
- **Action tests**: `tests/test_phase8_actions.py` — **22 passed** (16 original + 6 Wave A).
- **client.js**: `endpoints.allowedActions()`, `fireAssetAction(assetId,action,args)`,
  `fireApplicationAction(name,action,args)`, `listAssets({category})`, `listApplications()`.
- **listProjects() is EMPTY (count:0)** — applications filtered `type:project` is canonical;
  ProjectCard/listProjects retired for the lens home.
- **nginx_detail has TWO blocks per server_name** (:80 weak null + :443 authoritative w/ upstream_port).
  `ssl_not_after`/`ssl_issuer` come back null (known open item — cert parse perms).
- Build always clean except the pre-existing **>500 kB chunk warning** (Phase 5 lazy-route fixes it).

## 3b. File inventory (this session) + backups
NEW: `frontend/src/components/TopologyLane.jsx`, `frontend/src/components/ActionBar.jsx`,
`frontend/src/hooks/useAllowedActions.js`, `frontend/src/registry/cards.js`,
`frontend/src/pages/LensHome.jsx`, `REGISTRY_SPEC.md`.
EDITED (backups in repo): `app/actions.py` (.bak.v7-351, .bak.v7-352), `app/api/routers/actions.py`
(.bak.v7-352b), `tests/test_phase8_actions.py` (.bak.v7-352), `frontend/src/components/
ActionButton.jsx`, `frontend/src/pages/ApplicationDetail.jsx` (.bak.v7), `frontend/src/App.jsx`
(.bak.v7b/.v7c), `frontend/src/pages/Applications.jsx` (.bak.v7b), `frontend/src/pages/
ApplicationPanel.jsx` (.bak.v7b), `frontend/src/components/ActionBar.jsx` (.bak.v7-355/.355c/.355d).

---

## 4. Open items (deferred — pick up after motion pass)

- **3.5.6m motion pass** — §1. FIRST task.
- **Brand→home link** — top-left "InfraDocs" should link to `/`. Header.jsx edit. NOT done yet.
- **ActionBar on remaining surfaces** — nginx node (test/reload), lens-home project cards
  (application-level up/down/restart via `fireApplicationAction`), storage/port nodes (read-only or
  Wave B). Only the container node has it so far.
- **3.5.6 Wave B actions** — prune (image/volume), recreate, port identify/kill, scan triggers,
  next-run, storage inspect. Backend dispatch + 1 registry row each.
- **3.5.7 audit surfacing** — show last-action status chip on each card (actions already logged).
- **Resources vs Dashboard tab** — currently both render `<Dashboard/>`. Decide: merge (drop
  Resources, Dashboard = charts + registry tiles) or build distinct Resources registry-tile view.
- **git** — session work likely still uncommitted; Operator to commit. Confirm remote/branch first.
- **Known carryovers**: ssl cert parse (null), timer units not in `deploy/`, chunk-size warning.

---

## 5. Phase 3.5 progress (from REGISTRY_SPEC.md §5)
- [x] 3.5.1 backend registry refactor (ACTION_REGISTRY, self-protect centralized) — 16/16 green
- [x] 3.5.2 Wave A executor actions — 22/22 green; /api/actions/allowed extended
- [x] 3.5.3 frontend CARD_REGISTRY
- [x] 3.5.4 ActionBar + useAllowedActions
- [~] 3.5.5 retrofit shapes — container lane node DONE; nginx node, lens cards, modal PENDING;
       landing fixes (Dashboard default) DONE; brand→home link PENDING
- [ ] 3.5.6m MOTION PASS (next)
- [ ] 3.5.6 Wave B actions
- [ ] 3.5.7 audit surfacing