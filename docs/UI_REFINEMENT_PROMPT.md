# UI Refinement — Fresh Chat Prompt

Paste everything below the `--- START ---` line into a new claude.ai conversation as your first message. Attach screenshots of pages you want reviewed.

The prompt is self-contained: Claude won't have access to your filesystem, so the prompt includes enough context for it to reason about the design. After the AI responds with suggested changes, you bring them back to a Claude Code session in this repo to apply them.

---

--- START ---

You are reviewing the UI of **InfraDocs V6** — a single-host infrastructure dashboard I built. It scans an OCI host every 6 hours, aggregates everything (Docker containers, compose files, systemd units, nginx sites, listening ports, mounts), correlates them into per-application documents, and exposes the data via FastAPI + a React frontend.

## What the dashboard shows

Every asset on the host belongs to **exactly one bucket**:
- a **project folder** under `~/projects/<name>` (e.g., `openwebui`, `OCI_Dashboard`, `InfraDocs_V6`, `raveuploader_rws`, `carp`), OR
- the **System** bucket (catch-all for host-level things — root mount, SSH port, etc.)

There are also two first-class registries:
- **Ports registry** — every port we have evidence of (listening, declared in compose, nginx upstream, systemd `--port` flag), deduped per (port, proto), with multi-source evidence
- **Storage registry** — unifies mounts, docker volumes, project trees, and bind mounts into one inventory

And a Phase 8 **operational layer**: action buttons (start/stop/restart/logs) on containers and systemd units, with a full audit log of who did what when.

## Stack

- React 19 + Vite 8
- Tailwind 3 (dark theme; palette below)
- React Router 7
- TanStack Query 5 (data fetching)
- axios for HTTP basic auth

## Visual language to preserve

Dark theme. Tailwind custom palette:

```js
bg: {
  base:  "#0b1220",   // app background
  panel: "#111a2e",   // sidebar
  card:  "#16213e",   // card surfaces
  hover: "#1c2a4a",   // hovered rows / card borders
},
accent: { DEFAULT: "#3b82f6", dim: "#1e40af" }   // blue accent
```

Component conventions:
- **Cards**: `bg-bg-card border border-bg-hover rounded-lg p-4`
- **Section labels**: `text-xs uppercase tracking-wide text-slate-400`
- **Stat values**: `text-2xl font-semibold`
- **Sub-text**: `text-xs text-slate-500`
- **Active nav**: `bg-accent/20 text-accent`

## Pages currently in the build

| Route | Purpose |
|---|---|
| `/` | Dashboard — top-line counts + recent scans + quick project list |
| `/applications` | List of correlated application documents (one card per project + System) |
| `/applications/:name` | Rich detail: containers, compose file, nginx sites, URLs, ports, volumes, env keys, total disk, action buttons |
| `/projects` | Project list with health scores |
| `/projects/:name` | Per-project asset table (older view; less rich than /applications/:name) |
| `/assets` | Flat list of all assets with category/project filters |
| `/ports` | Ports registry table + filters + a live "Probe range" tool |
| `/storage` | Storage registry: kind tabs (mount / volume / project_tree / bind_mount), totals, owner breakdown |
| `/actions` | Audit log of every action attempt (action, actor, asset, status, timestamp, refused_reason) |
| `/scans` | Scan history + "Trigger scan" button |

Sidebar groups: **Overview** (Dashboard) · **Inventory** (Applications, Projects, Ports, Storage, All Assets) · **Activity** (Scans, Actions Log) · **By Category** (quick filters into /assets per category).

## Action button safety model

- **Read-only actions** (`logs`, `status`, `test`) fire immediately.
- **Mutating actions** (`start`, `stop`, `restart`, `up`, `down`, `reload`) show a JS `confirm()` first.
- **Self-protected services** (anything starting with `infradocs-v6-`) have the button visibly disabled with a tooltip — the API would 409 anyway.

## What I want from you

Look at the screenshots I attach and give me **specific, actionable feedback** organized as:

1. **What works** — keep me from undoing things that are good.
2. **Information hierarchy issues** — anything that buries important info or surfaces low-value data prominently.
3. **Layout / spacing / density** — too sparse? too cramped? wrong column proportions?
4. **Visual polish** — color use, typography, icon use (or absence), states (loading, empty, error, hover).
5. **Interaction issues** — anything confusing about how to drill down, filter, navigate.
6. **Concrete suggestions** — for each issue, propose a specific fix I can hand back to a Claude Code session in the repo. Reference Tailwind class names and the conventions above.

Optional: if you see opportunities for visualizations (sparkline of disk usage per project, sankey of port → container → nginx → URL, treemap of storage by owner), call them out — I want to know what would meaningfully add value vs. just look fancy.

**Bias toward specificity.** "The dashboard looks good" is useless. "The Last Scan card on the dashboard should show the scan's `total_assets - System count` so you can see project-attributable changes at a glance" is useful.

Don't redesign blindly — assume I have constraints I haven't shared. If a change is non-obvious, explain the why so I can decide.

--- END ---
