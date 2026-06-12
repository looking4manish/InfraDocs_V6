import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import {
  Search, CornerDownLeft, LayoutDashboard, Boxes, Folders, Plug,
  Layers, ScanLine, History, Files, RefreshCw, Container, Globe, Cog, HardDrive,
} from "lucide-react";
import { endpoints } from "../api/client";
import { normalizeList } from "../lib/attention";
import { useDrawer } from "./DrawerProvider";
import { cn } from "../lib/cn";

const NAV = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard },
  { label: "Applications", path: "/applications", icon: Boxes },
  { label: "Projects", path: "/projects", icon: Folders },
  { label: "Assets", path: "/assets", icon: Files },
  { label: "Ports", path: "/ports", icon: Plug },
  { label: "Storage", path: "/storage", icon: Layers },
  { label: "Scans", path: "/scans", icon: ScanLine },
  { label: "Actions log", path: "/actions", icon: History },
];

const CAT_ICON = {
  docker_container: Container, docker_image: Boxes, docker_volume: HardDrive,
  docker_network: Plug, nginx_server_block: Globe, systemd_service: Cog,
  systemd_timer: Cog, network_port: Plug, storage_mount: HardDrive,
  docker_compose: Files,
};

function score(q, s) {
  if (!q) return 1;
  s = s.toLowerCase();
  const idx = s.indexOf(q);
  if (idx === 0) return 100 - s.length * 0.1;
  if (idx > 0) return 60 - idx;
  let i = 0;
  for (const ch of s) if (ch === q[i]) i++;
  return i === q.length ? 20 - s.length * 0.05 : -1;
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const { openDrawer } = useDrawer();

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o); setQ(""); setSel(0);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { if (open) setTimeout(() => inputRef.current?.focus(), 30); }, [open]);

  const apps = useQuery({
    queryKey: ["palette-apps"],
    queryFn: () => endpoints.listApplications().then((r) => r.data),
    enabled: open, staleTime: 60000,
  });
  const assets = useQuery({
    queryKey: ["palette-assets"],
    queryFn: () => endpoints.listAssets().then((r) => r.data),
    enabled: open, staleTime: 60000,
  });

  const entries = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = [];
    for (const n of NAV)
      out.push({ group: "Navigate", label: n.label, icon: n.icon,
        s: score(needle, n.label), run: () => navigate(n.path) });
    out.push({ group: "Actions", label: "Trigger scan now", icon: RefreshCw,
      s: score(needle, "trigger scan now"),
      run: () => endpoints.triggerScan() });
    for (const a of normalizeList(apps.data, ["applications", "items", "results", "apps"]))
      out.push({ group: "Applications", label: a.name, icon: Boxes,
        hint: a.type, s: score(needle, a.name),
        run: () => openDrawer({ type: "application", name: a.name }) });
    for (const a of normalizeList(assets.data, ["assets", "items", "results"])) {
      const id = a.asset_id || a._id || a.id;
      if (!id) continue;
      out.push({ group: "Assets", label: a.name, icon: CAT_ICON[a.category] || Files,
        hint: a.category, s: score(needle, `${a.name} ${a.category}`),
        run: () => openDrawer({ type: "asset", id, label: a.name }) });
    }
    return out.filter((e) => e.s >= 0).sort((x, y) => y.s - x.s).slice(0, 14);
  }, [q, apps.data, assets.data, navigate, openDrawer]);

  useEffect(() => { setSel(0); }, [q, open]);

  const exec = (e) => { if (!e) return; setOpen(false); e.run(); };

  const onInputKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, entries.length - 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    if (e.key === "Enter") { e.preventDefault(); exec(entries[sel]); }
  };

  let lastGroup = null;
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="cp-bg" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]"
          />
          <motion.div
            key="cp" initial={{ opacity: 0, scale: 0.975, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.975, y: -8 }}
            transition={{ type: "spring", stiffness: 480, damping: 36 }}
            className="fixed z-50 left-1/2 -translate-x-1/2 top-[14vh] w-[92vw] max-w-xl rounded-xl bg-bg-panel border border-bg-hover shadow-2xl overflow-hidden"
          >
            <div className="flex items-center gap-3 px-4 h-13 border-b border-bg-hover py-3.5">
              <Search size={16} className="text-zinc-500 shrink-0" />
              <input
                ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)}
                onKeyDown={onInputKey}
                placeholder="Search applications, assets, pages…"
                className="flex-1 bg-transparent text-[14px] text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
              />
              <kbd className="text-[10px] text-zinc-600 border border-bg-hover rounded px-1.5 py-0.5 font-mono">esc</kbd>
            </div>
            <div className="max-h-[46vh] overflow-y-auto py-1.5">
              {entries.length === 0 && (
                <div className="px-4 py-6 text-[13px] text-zinc-600">Nothing matches.</div>
              )}
              {entries.map((e, i) => {
                const head = e.group !== lastGroup; lastGroup = e.group;
                const Icon = e.icon;
                return (
                  <div key={`${e.group}-${e.label}-${i}`}>
                    {head && (
                      <div className="px-4 pt-2.5 pb-1 text-[10px] font-medium uppercase tracking-[0.08em] text-zinc-600">
                        {e.group}
                      </div>
                    )}
                    <button
                      onMouseEnter={() => setSel(i)} onClick={() => exec(e)}
                      className={cn(
                        "w-full flex items-center gap-3 px-4 py-2 text-left text-[13.5px] transition",
                        i === sel ? "bg-accent/15 text-zinc-50" : "text-zinc-400 hover:text-zinc-200"
                      )}
                    >
                      <Icon size={15} className={cn("shrink-0", i === sel ? "text-accent-soft" : "text-zinc-600")} />
                      <span className="truncate">{e.label}</span>
                      {e.hint && <span className="ml-auto text-[11px] text-zinc-600 font-mono shrink-0">{e.hint}</span>}
                      {i === sel && !e.hint && <CornerDownLeft size={13} className="ml-auto text-zinc-600 shrink-0" />}
                    </button>
                  </div>
                );
              })}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
