import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Boxes, ChevronLeft } from "lucide-react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";
import { formatBytes } from "../components/Bytes";
import ApplicationDetail from "./ApplicationDetail";

function hasRuntime(a) {
  return (
    (a.components_count ?? 0) > 0 ||
    (a.containers?.length || 0) > 0 ||
    (a.systemd_units?.length || 0) > 0 ||
    (a.listening_ports?.length || 0) > 0
  );
}

// One selectable master-list row. Selection is a URL param, so clicking only
// swaps the detail pane — the list stays mounted (true master-detail).
function AppListItem({ app, active, onSelect }) {
  const live = hasRuntime(app);
  const dot = !live ? "bg-zinc-600" : app.internet_exposed ? "bg-emerald-400" : "bg-sky-400";
  return (
    <button
      type="button"
      onClick={() => onSelect(app.name)}
      className={cn(
        "w-full text-left px-3 py-2.5 border-l-2 transition outline-none",
        active
          ? "border-accent bg-accent/[0.08]"
          : "border-transparent hover:bg-white/[0.03] focus-visible:bg-white/[0.04]"
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)} />
        <span className={cn("text-[13.5px] font-medium truncate", !live && "text-zinc-500")}>
          {app.name}
        </span>
        {app.internet_exposed && (
          <span className="ml-auto text-[9.5px] font-semibold px-1.5 py-px rounded bg-emerald-500/15 text-emerald-300 shrink-0">
            {app.cloudflare ? "CF" : "live"}
          </span>
        )}
      </div>
      <div className="text-[11px] text-zinc-600 font-mono tabular-nums mt-1 truncate">
        {app.components_count ?? 0} comp · {app.listening_ports?.length || 0} ports · {formatBytes(app.total_size_bytes)}
      </div>
    </button>
  );
}

export default function Applications() {
  const [filter, setFilter] = useState("all");
  const [params, setParams] = useSearchParams();
  const selected = params.get("sel") || null;

  const select = (name) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("sel", name);
      return next;
    });
  const clearSelection = () =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("sel");
      return next;
    });

  const q = useQuery({
    queryKey: ["applications"],
    queryFn: () => endpoints.listApplications().then((r) => r.data),
  });

  const filtered = useMemo(() => {
    const apps = q.data?.applications || [];
    if (filter === "exposed") return apps.filter((a) => a.internet_exposed);
    if (filter === "projects") return apps.filter((a) => a.type === "project");
    if (filter === "system") return apps.filter((a) => a.type === "system");
    return apps;
  }, [q.data, filter]);

  const counts = useMemo(() => {
    const all = q.data?.applications || [];
    return {
      all: all.length,
      exposed: all.filter((a) => a.internet_exposed).length,
      projects: all.filter((a) => a.type === "project").length,
      system: all.filter((a) => a.type === "system").length,
    };
  }, [q.data]);

  const filters = [
    ["all", "All", counts.all],
    ["projects", "Projects", counts.projects],
    ["system", "System", counts.system],
    ["exposed", "Exposed", counts.exposed],
  ];

  return (
    <div className="flex gap-4 h-[calc(100vh-7rem)]">
      {/* MASTER — list (hidden on mobile once something is selected) */}
      <div
        className={cn(
          "w-full lg:w-[320px] shrink-0 flex flex-col rounded-xl neon-panel overflow-hidden",
          selected && "hidden lg:flex"
        )}
      >
        <div className="px-3.5 pt-3.5 pb-2 shrink-0">
          <h1 className="text-[16px] font-semibold tracking-tight">Applications</h1>
          <div className="flex flex-wrap gap-1 mt-2.5">
            {filters.map(([k, label, count]) => (
              <button
                key={k}
                onClick={() => setFilter(k)}
                className={cn(
                  "px-2 py-0.5 rounded-md text-[11px] border transition",
                  filter === k
                    ? "border-accent/40 bg-accent/10 text-accent-soft"
                    : "border-bg-hover text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
                )}
              >
                {label} <span className="text-zinc-600 tabular-nums">{count}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto border-t border-bg-hover/60 divide-y divide-bg-hover/40">
          {q.isLoading && <div className="text-zinc-500 text-sm py-10 text-center">Loading…</div>}
          {q.isError && <div className="text-red-400 text-sm px-3 py-4">Failed: {String(q.error)}</div>}
          {filtered.map((app) => (
            <AppListItem
              key={app.application_id || app.name}
              app={app}
              active={selected === app.name}
              onSelect={select}
            />
          ))}
          {q.data && filtered.length === 0 && (
            <div className="text-zinc-500 text-sm px-4 py-6">No applications match.</div>
          )}
        </div>
      </div>

      {/* DETAIL — pane (hidden on mobile until something is selected) */}
      <div
        className={cn(
          "flex-1 min-w-0 overflow-y-auto",
          !selected && "hidden lg:block"
        )}
      >
        {selected ? (
          <div className="max-w-[1100px]">
            <button
              onClick={clearSelection}
              className="lg:hidden inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-accent mb-3"
            >
              <ChevronLeft size={14} /> All applications
            </button>
            <ApplicationDetail name={selected} />
          </div>
        ) : (
          <div className="h-full grid place-items-center text-center">
            <div className="text-zinc-600">
              <Boxes size={34} className="mx-auto mb-3 opacity-40" />
              <div className="text-[13px]">Select an application to see its topology, components, and actions.</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
