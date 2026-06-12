// V7 Phase 2 — attention rules v1. Pure functions over data we already have.

export function normalizeList(d, keys) {
  if (Array.isArray(d)) return d;
  for (const k of keys) if (Array.isArray(d?.[k])) return d[k];
  return [];
}

const DAY = 86400000;

export function computeAttention(apps, lastScanAt) {
  const items = [];
  const now = Date.now();

  for (const a of apps || []) {
    const hyg = a.hygiene || {};
    for (const c of hyg.exited_restart_always || [])
      items.push({ sev: 2, app: a.name, kind: "docker",
        text: `${c} exited despite restart=always` });
    for (const i of a.resilience?.issues || [])
      items.push({ sev: 2, app: a.name, kind: "resilience", text: i });
    if ((hyg.dangling_images || []).length)
      items.push({ sev: 1, app: a.name, kind: "docker",
        text: `${hyg.dangling_images.length} dangling image(s)` });
    if ((hyg.orphaned_volumes || []).length)
      items.push({ sev: 1, app: a.name, kind: "docker",
        text: `orphaned volume(s): ${hyg.orphaned_volumes.join(", ")}` });
    for (const ng of a.nginx_detail || []) {
      if (!ng.ssl_not_after) continue;
      const t = Date.parse(ng.ssl_not_after);
      if (Number.isNaN(t)) continue;
      const days = Math.floor((t - now) / DAY);
      if (days < 7)
        items.push({ sev: 3, app: a.name, kind: "certs",
          text: `cert ${ng.server_name} expires in ${days}d` });
      else if (days < 30)
        items.push({ sev: 2, app: a.name, kind: "certs",
          text: `cert ${ng.server_name} expires in ${days}d` });
    }
    if (a.type === "project" && (a.components_count || 0) > 0 &&
        !(a.links || []).length)
      items.push({ sev: 1, app: a.name, kind: "evidence",
        text: "assets present but no linking evidence" });
  }

  if (lastScanAt) {
    const h = (now - lastScanAt) / 3600000;
    if (h > 48)
      items.push({ sev: 3, app: null, kind: "scans",
        text: `last scan ${Math.floor(h / 24)}d ago` });
    else if (h > 12)
      items.push({ sev: 2, app: null, kind: "scans",
        text: `last scan ${Math.floor(h)}h ago` });
  }

  items.sort((x, y) => y.sev - x.sev);
  return items;
}

export function freshness(lastScanAt) {
  if (!lastScanAt) return { label: "no scans", level: "bad" };
  const m = Math.floor((Date.now() - lastScanAt) / 60000);
  const label =
    m < 60 ? `${m}m` :
    m < 2880 ? `${Math.floor(m / 60)}h` :
    `${Math.floor(m / 1440)}d`;
  return { label, level: m > 2880 ? "bad" : m > 720 ? "warn" : "ok" };
}

export function parseScanTime(scan) {
  for (const k of ["finished_at", "completed_at", "ended_at", "started_at",
                   "created_at", "timestamp", "time"]) {
    if (scan?.[k]) {
      const t = Date.parse(scan[k]);
      if (!Number.isNaN(t)) return t;
    }
  }
  return null;
}
