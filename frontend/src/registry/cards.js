// Card & Action Registry (Phase 3.5) — PRESENTATION ONLY.
// Backend (/api/actions/allowed) is authoritative on what is permitted + destructive.
// This file decides how each category looks: icon, label, shape, which fields to
// show, and per-action presentation (label + lucide icon name). Joined to the
// backend by the category string. Never decides permission.
//
// shapes: "entity" (dot/title/badges/stats + ActionBar) | "flow_node" (lane node)
//         | "tile" (registry hub) | "stat" (KPI, read-only)

// Per-action presentation. id MUST equal the backend action verb.
export const ACTION_META = {
  start:   { label: "Start",   icon: "Play" },
  stop:    { label: "Stop",    icon: "Square" },
  restart: { label: "Restart", icon: "RotateCw" },
  logs:    { label: "Logs",    icon: "ScrollText" },
  status:  { label: "Status",  icon: "Activity" },
  inspect: { label: "Inspect", icon: "Search" },
  stats:   { label: "Stats",   icon: "BarChart3" },
  enable:  { label: "Enable",  icon: "ToggleRight" },
  disable: { label: "Disable", icon: "ToggleLeft" },
  up:      { label: "Up",      icon: "ArrowUp" },
  down:    { label: "Down",    icon: "ArrowDown" },
  reload:  { label: "Reload",  icon: "RefreshCw" },
  test:    { label: "Test",    icon: "FlaskConical" },
  pull:    { label: "Pull",    icon: "Download" },
  prune:    { label: "Prune",    icon: "Trash2" },
  recreate: { label: "Recreate", icon: "RefreshCcw" },
  trigger:  { label: "Run now",  icon: "PlayCircle" },
};

// Per-category presentation. `fields` lists what an entity card shows.
export const CARD_REGISTRY = {
  docker_container: {
    icon: "Box",
    label: "Container",
    shape: "entity",
    accent: "violet",
    fields: [
      { key: "image", label: "image" },
      { key: "restart_policy", label: "restart" },
      { key: "running", label: "state", fmt: "running" },
    ],
    // Preferred display order; intersected with backend-allowed at render time.
    actions: ["logs", "inspect", "stats", "restart", "stop", "start"],
    primary: "logs",
  },
  docker_compose: {
    icon: "Layers",
    label: "Compose",
    shape: "entity",
    accent: "violet",
    fields: [{ key: "file_path", label: "file" }],
    actions: ["up", "restart", "recreate", "down"],
    primary: "up",
  },
  systemd_service: {
    icon: "Cog",
    label: "Service",
    shape: "entity",
    accent: "sky",
    fields: [{ key: "status", label: "state" }],
    actions: ["status", "logs", "restart", "enable", "disable", "start", "stop"],
    primary: "status",
  },
  systemd_timer: {
    icon: "Clock",
    label: "Timer",
    shape: "entity",
    accent: "sky",
    fields: [{ key: "next_run", label: "next" }],
    actions: ["status", "trigger", "restart", "enable", "disable", "start", "stop"],
    primary: "status",
  },
  nginx_server_block: {
    icon: "Server",
    label: "Nginx",
    shape: "flow_node",
    accent: "violet",
    fields: [
      { key: "listen_ports", label: "listen" },
      { key: "upstream_port", label: "upstream" },
    ],
    actions: ["test", "reload"],
    primary: "test",
  },
  docker_image: {
    icon: "Package",
    label: "Image",
    shape: "entity",
    accent: "amber",
    fields: [
      { key: "tags", label: "tags" },
      { key: "is_dangling", label: "dangling" },
    ],
    actions: ["pull", "prune"],
    primary: "pull",
  },
  // Non-actionable shapes (no backend actions; render read-only).
  network_port: { icon: "Plug", label: "Port", shape: "flow_node", accent: "violet",
    fields: [{ key: "port", label: "port" }, { key: "process", label: "proc" }], actions: [] },
  docker_volume: { icon: "Database", label: "Volume", shape: "entity", accent: "amber",
    fields: [{ key: "mountpoint", label: "mount" }, { key: "size_bytes", label: "size", fmt: "bytes" }],
    actions: ["inspect", "prune"], primary: "inspect" },
  storage_mount: { icon: "HardDrive", label: "Storage", shape: "flow_node", accent: "violet",
    fields: [{ key: "mountpoint", label: "mount" }, { key: "size_bytes", label: "size", fmt: "bytes" }],
    actions: ["inspect"], primary: "inspect" },
};

// Helper: presentation actions for a category, intersected with backend-allowed.
export function actionsFor(category, allowedMap) {
  const reg = CARD_REGISTRY[category];
  if (!reg) return [];
  const allowed = new Set(allowedMap?.[category] || []);
  return (reg.actions || []).filter((a) => allowed.has(a));
}

export function isDestructive(category, action, destructiveMap) {
  return new Set(destructiveMap?.[category] || []).has(action);
}
