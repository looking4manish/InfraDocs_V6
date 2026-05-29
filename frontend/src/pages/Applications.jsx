import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useOutlet, useNavigate, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { endpoints } from "../api/client";
import AppCard from "../components/AppCard";

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

  return (
    <>
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-semibold">Applications</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              One document per <code>~/projects/&lt;name&gt;</code> folder + the
              System bucket. Each card stitches together the app's containers,
              compose file, nginx sites, ports, volumes, and disk usage.
            </p>
          </div>
        </div>

        <div className="flex gap-2 mb-4 text-sm">
          {[
            ["all", "All", counts.all],
            ["projects", "Project apps", counts.projects],
            ["system", "System", counts.system],
            ["exposed", "Internet-exposed", counts.exposed],
          ].map(([k, label, count]) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`px-3 py-1 rounded border text-xs ${
                filter === k
                  ? "border-accent text-accent bg-accent/10"
                  : "border-bg-hover text-slate-400 hover:text-slate-200"
              }`}
            >
              {label} <span className="text-slate-500">· {count}</span>
            </button>
          ))}
        </div>

        {q.isLoading && <div className="text-slate-400 text-sm">Loading…</div>}
        {q.isError && (
          <div className="text-rose-300 text-sm">Failed: {String(q.error)}</div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((app) => (
            <AppCard
              key={app.application_id || app.name}
              app={app}
              active={selected === app.name}
            />
          ))}
        </div>
        {q.data && filtered.length === 0 && (
          <div className="text-slate-400 text-sm">No applications match.</div>
        )}
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="app-panel-backdrop"
            className="fixed inset-0 z-40 bg-black/50"
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
            className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-2xl bg-bg-base border-l border-bg-hover shadow-2xl"
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
