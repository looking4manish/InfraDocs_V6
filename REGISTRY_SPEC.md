# InfraDocs V7 — Card & Action Registry Spec (Phase 3.5)

> **Purpose:** single source of truth for the *card + action registry* — the data-driven spine that
> turns every asset, at every altitude (lens-home grid → topology lane → nested node), into a card
> that both **shows** information and **operates** on the entity. Built once; consumed by Phases
> 3–7. To resume in any session, attach this file + `V7_PLAN.md` + the latest handoff and say:
> *"Resume InfraDocs V7 Phase 3.5 at Step N. C.H.A.I.N. protocol."*
>
> - **Status:** Spec drafted — implementation not started
> - **Repo:** `/home/msinha/projects/InfraDocs_V6` (OCI, user `msinha`)
> - **Protocol:** C.H.A.I.N. — one action/turn, State Block every turn, heredoc-only writes, no assumed filenames

---

## 1. Why this exists (the problem)

V6/early-V7 cards are *labels that happen to navigate*. The backend already permits operational
actions (`app/actions.py` → `ALLOWED_ACTIONS`, served at `/api/actions/allowed`) but the UI only
surfaces them on one detail view. Meanwhile scanners gather actionable entities (images, volumes,
ports, timers) the action layer ignores.

**Goal:** a card *contains content **and** the actions valid for its subject* (NN/g's own definition).
Every card, everywhere, is operable — with progressive disclosure so actions never drown the data.

---

## 2. Architecture — split ownership (the core contract)

Two registries, joined by the **category string** (`docker_container`, `systemd_service`, …):

```
            category string  ─────────────┐
                                           │ (the join key)
  BACKEND  (authoritative on PERMISSION)   │   FRONTEND (authoritative on PRESENTATION)
  app/actions.py :: ACTION_REGISTRY        │   frontend/src/registry/cards.js :: CARD_REGISTRY
  ─────────────────────────────────        │   ─────────────────────────────────────────────
  per category:                            │   per category:
    allowed_actions: set[str]              │     icon, label, accent
    destructive: set[str]    ──────────────┘     shape: "entity" | "flow_node" | "tile"
    self_protect rules                           fields: [ {key,label,fmt} … ]   (what to show)
    dispatch(asset, action, args)                actions: [ {id,label,icon,intent,confirm?} … ]
    served at /api/actions/allowed               (presentation only; never decides permission)
```

**Rules:**
1. **Backend decides *what is permitted*** — period. A button the backend doesn't allow is never
   fireable; the UI greys/hides it based on the live `/api/actions/allowed` fetch, not its own guess.
2. **Frontend decides *how it looks*** — icon, label, ordering, which fields render, hover behavior.
   Lucide icon names live in JS, never in Python (no presentation in the executor).
3. **The category string is the only coupling.** Add a scanner category → add one backend registry
   row (permission) + one frontend registry row (presentation) → a working, operable card appears.
4. **Destructive = confirm-gated** (existing `window.confirm` path in `ActionButton`) **and**
   `infradocs-v6-*` stays self-protected (API 409, button disabled with reason).
5. **No phantom buttons** — an action ships only if a scanner already substantiates the data it needs.

---

## 3. Action taxonomy (the full surface)

Legend: ✅ exists today · ➕ to add · 🔒 destructive (confirm + maybe self-protect) · ⚠ gated/needs sudo

| Category | Today | Add | Notes / scanner-grounding |
|---|---|---|---|
| `docker_container` | start, stop🔒, restart🔒, logs | ➕ inspect, ➕ stats, ➕ recreate🔒 | image/ports/health already scanned; recreate = pull+up |
| `docker_compose` | up, down🔒, restart🔒 | ➕ pull, ➕ ps | compose_file path known |
| `docker_image` | — | ➕ pull, ➕ prune🔒 (if `is_dangling`) | scanner knows `is_dangling`, `tags`, `in_use` |
| `docker_volume` | — | ➕ inspect, ➕ ls (read-only), ➕ prune🔒 (if orphaned) | `mountpoint`, orphan state known |
| `systemd_service` | start, stop🔒, restart🔒, logs, status | ➕ enable, ➕ disable🔒 | enable/disable = the reboot-resilience lever (V7 goal) |
| `systemd_timer` | start, stop🔒, restart🔒, status | ➕ enable, ➕ disable🔒, ➕ next-run | timer schedule scannable |
| `nginx_server_block` | test, reload | *(keep as-is — correct & safe)* | — |
| `network_port` | — | ➕ identify (owning proc), ➕ kill🔒⚠ | `port.py` knows pid/process |
| `application` (aggregate) | restart-all | ➕ up, ➕ down🔒, ➕ pull-all | already fans out to members |
| `host` / `scan` | — | ➕ trigger-scan, ➕ view-last-log | scan endpoint exists (`/api/scans`) |
| `storage_mount` | — | ➕ inspect (df/usage) | mount facts scanned |

Phasing of the surface (so a session can stop cleanly):
- **Wave A (safe core, proves the pattern):** container inspect/stats; systemd enable/disable;
  application up/down/restart; image pull. Non-destructive-leaning, high value.
- **Wave B (full surface):** prune (image/volume), recreate, port identify/kill, scan triggers,
  next-run, storage inspect.

---

## 4. Card shapes (presentation catalog — ~4, not one-per-category)

The registry maps each category to **one of these shapes**, not a bespoke component:

1. **`entity` card** — the workhorse. Dot (state) · title · type/exposed badges · mono micro-stats ·
   **hover-reveal ActionBar**. Used by: lens-home project cards, container/service/volume cards.
2. **`flow_node`** — the topology-lane node (already built in `TopologyLane.jsx`). Same data, lane
   geometry; ActionBar appears in a popover on the node (so the lane stays clean).
3. **`tile`** — big-number registry tile (Resources lens: Ports/Storage/Domains/DBs/Schedules/Backups).
   Action = navigate to registry; rarely operable itself.
4. **`stat`** — KPI strip card (Dashboard). Read-only by definition (one number + trend).

**Shared primitive: `<ActionBar entity={…} />`** — the single component every shape uses. It:
- fetches/reads the allowed-actions map (cached via TanStack Query on `/api/actions/allowed`),
- intersects category's allowed set with the frontend registry's action list,
- renders primary action inline + rest in a hover bar or `⋯` overflow,
- reuses existing `ActionButton` (icons, confirm, self-protect, output modal) under the hood.

Progressive disclosure (research-backed): resting card shows info only; **hover reveals the
ActionBar**; destructive actions sit in overflow, never inline. One card = one subject's actions.

---

## 5. Build phases (dependency order — every phase ships something runnable)

- [ ] **3.5.1 — Backend registry refactor.** Promote `ALLOWED_ACTIONS` → `ACTION_REGISTRY`
  (allowed + destructive + self_protect per category). Keep `/api/actions/allowed` shape
  backward-compatible (additive `destructive` map). Extend tests.
- [ ] **3.5.2 — Backend executor: Wave A actions.** Implement container inspect/stats, systemd
  enable/disable, application up/down, image pull in `dispatch()`. Fixture tests per action.
- [ ] **3.5.3 — Frontend `CARD_REGISTRY`** (`frontend/src/registry/cards.js`): category → icon,
  label, shape, fields, actions. Pure data. Unit-renderable.
- [ ] **3.5.4 — `<ActionBar/>` primitive** + `useAllowedActions()` hook. Wraps `ActionButton`.
  Hover-reveal + overflow. The one component all shapes consume.
- [ ] **3.5.5 — Retrofit shapes onto registry:** lens-home cards → `entity` shape + ActionBar;
  lane nodes → ActionBar popover; (tiles/stat already minimal).
- [ ] **3.5.6 — Wave B actions** (backend + registry rows): prune, recreate, port kill, scan
  triggers, next-run, storage inspect. Each: backend dispatch + 1 registry row + it renders.
- [ ] **3.5.7 — Audit surfacing:** every fired action already writes to the actions log
  (`record_action`); ensure each card's ActionBar shows last-action status inline (footer chip).

**Sequencing rule:** 3.5.1→3.5.4 is the spine; nothing visual is built before the ActionBar exists,
so no card is built twice. Wave B is purely additive registry rows after the spine is proven.

---

## 6. Landing + chrome fixes (folded in here, small)

From UAT, ship alongside 3.5.5:
- Default lens = **Dashboard** (the former "Resources" content; rename tab to "Dashboard").
- **Brand top-left → links to `/`** (home).
- Lens tab order: `Dashboard · Projects · Servers · Resources · Assets` (Dashboard first/home).

---

## 7. Key reference (carried for resume)

| Item | Value |
|---|---|
| Backend allow-list | `app/actions.py` :: `ALLOWED_ACTIONS` (5 categories today) → becomes `ACTION_REGISTRY` |
| Allowed API | `GET /api/actions/allowed` → `{allowed:{category:[…]}}` (extend with `destructive`) |
| Fire endpoints | `POST /api/assets/{asset_id}/action` · `POST /api/applications/{name}/action` |
| Self-protect | `infradocs-v6-*` assets → API 409 (`SelfActionRefused`); UI disables w/ reason |
| Existing UI action unit | `frontend/src/components/ActionButton.jsx` (icons✓, confirm, modal, self-protect) |
| New frontend files | `frontend/src/registry/cards.js` · `frontend/src/components/ActionBar.jsx` · `hooks/useAllowedActions.js` |
| Card shapes live | lens cards in `LensHome.jsx` · lane nodes in `TopologyLane.jsx` |
| Guard rails | no phantom buttons · backend owns permission · destructive=confirm+self-protect · additive only |