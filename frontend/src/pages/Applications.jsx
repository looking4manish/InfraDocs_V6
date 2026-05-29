import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useOutlet, useNavigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";
import AppRow from "../components/AppRow";

export default function Applications() {
  const [filter, setFilter] = useState("all");
  const outlet = useOutlet();
  const navigate = useNavigate();
  const location = useLocation();
  const isOpen = Boolean(outlet);
  const selected = isOpen
    ? decodeURIComponent(location.pathname.replace(/^\/applications\/?/, ""))
    : null;

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e) => {
      if (e.key === "Escape") navigate("/applications");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, navigate]);

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
    ["exposed", "Internet-exposed", counts.exposed],
  ];

  return (
    <>
      <div className="max-w-5xl">
        <h1 className="text-[22px] font-semibold tracking-tight">Applications</h1>
        <p className="text-[13px] text-zinc-500 mt-1">
          One document per{" "}
          <span className="font-mono text-zinc-400">~/projects/&lt;name&gt;</span>{" "}
          folder plus the System bucket — containers, compose, nginx, ports,
          volumes and disk, stitched together.
        </p>

        <div className="flex gap-1.5 mt-4 mb-3">
          {filters.map(([k, label, count]) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={cn(
                "px-2.5 py-1 rounded-md text-[12px] border transition",
                filter === k
                  ? "border-accent/40 bg-accent/10 text-accent-soft"
                  : "border-bg-hover text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
              )}
            >
              {label}{" "}
              <span className="text-zinc-600 tabular-nums">{count}</span>
            </button>
          ))}
        </div>

        {q.isLoading && (
          <div className="text-zinc-500 text-sm py-10 text-center">Loading…</div>
        )}
        {q.isError && (
          <div className="text-red-400 text-sm">Failed: {String(q.error)}</div>
        )}

        {q.data && (
          <div className="rounded-lg border border-bg-hover bg-bg-card/40 overflow-hidden divide-y divide-bg-hover/60">
            {filtered.map((app) => (
              <AppRow
                key={app.application_id || app.name}
                app={app}
                active={selected === app.name}
              />
            ))}
            {filtered.length === 0 && (
              <div className="text-zinc-500 text-sm px-4 py-6">
                No applications match.
              </div>
            )}
          </div>
        )}
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="app-panel-backdrop"
            className="fixed inset-0 z-40 bg-black/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => navigate("/applications")}
          />
        )}
        {isOpen && (
          <motion.aside
            key="app-panel-drawer"
            className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-2xl bg-bg-panel border-l border-bg-hover shadow-2xl"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", ease: "easeOut", duration: 0.28 }}
          >
            {outlet}
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
