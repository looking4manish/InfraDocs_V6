import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
import { Container, Cog, Globe, HardDrive, Package } from "lucide-react";
import ActionButton from "../components/ActionButton";
import { endpoints } from "../api/client";
import { formatBytes } from "../components/Bytes";
import { cn } from "../lib/cn";
import Dashboard from "./Dashboard";

const LENSES = ["Dashboard", "Projects", "Servers", "Web", "Assets"];

const SPRING = { type: "spring", stiffness: 400, damping: 36 };

// Stagger parent + child variants. reduce=true collapses to instant.
function gridVariants(reduce) {
  return {
    hidden: {},
    show: { transition: { staggerChildren: reduce ? 0 : 0.03 } },
  };
}
function cardVariants(reduce) {
  return reduce
    ? { hidden: { opacity: 1, y: 0 }, show: { opacity: 1, y: 0 } }
    : { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: SPRING } };
}

// Host facts — static lab truth until Phase 6 agents populate substrate live.
const HOSTS = [
  { id: "oci", name: "OCI", ip: "80.225.195.84", ts: "100.107.140.36", live: true },
  { id: "oci-p", name: "OCI-P", ip: "140.245.228.255", ts: "100.70.18.9", live: false,
    note: "MongoDB rs0 primary · MXH host" },
  { id: "n150", name: "N150", ip: null, ts: "100.72.146.5", live: false,
    note: "Nextcloud · Immich · AdGuard" },
  { id: "omen", name: "OMEN", ip: null, ts: "100.98.102.10", live: false,
    note: "Ollama · GPU workstation" },
];

function hasRuntime(a) {
  return (
    (a.components_count ?? 0) > 0 ||
    (a.containers?.length || 0) > 0 ||
    (a.systemd_units?.length || 0) > 0 ||
    (a.listening_ports?.length || 0) > 0
  );
}

// Attention weight: down/exposed-but-idle rises; healthy sinks.
function attentionScore(a) {
  let s = 0;
  if (a.internet_exposed && !hasRuntime(a)) s += 100; // exposed but nothing running
  if (!hasRuntime(a)) s += 10;
  if (a.internet_exposed) s += 5;
  s += a.components_count ?? 0;
  return -s; // higher concern first
}

function Chip({ icon: Icon, n, label }) {
  return (
    <span title={label} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border border-bg-hover text-[11px] text-zinc-400">
      <Icon size={12} className="opacity-80" /> {n}
    </span>
  );
}

function appFireWrapper(name, action) {
  return () =>
    endpoints.fireApplicationAction(name, action).then((res) => {
      const d = res?.data || {};
      const lines = (d.results || []).map(
        (r) => `${r.status === "success" ? "✓" : r.status === "skipped" ? "·" : "✗"} ${r.category} ${r.asset_name} → ${r.status}`
      );
      const ok = (d.results || []).filter((r) => r.status === "success").length;
      return { data: { status: ok > 0 ? "success" : "failed",
        stdout: `${action} on ${name} — ${d.targets || 0} target(s), ${ok} ok\n\n` + lines.join("\n"),
        stderr: "" } };
    });
}

function AppActionRow({ name }) {
  return (
    <div className="absolute bottom-3 right-3 z-[2] flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
      onClick={(e) => { e.stopPropagation(); e.preventDefault(); }}>
      {["restart", "up", "down"].map((v) => (
        <ActionButton key={v} action={v} label={v} size="xs" fire={appFireWrapper(name, v)} />
      ))}
    </div>
  );
}

function ProjectLensCard({ app, onOpen, reduce }) {
  const live = hasRuntime(app);
  const dot = !live ? "bg-zinc-600" : app.internet_exposed ? "bg-emerald-400" : "bg-sky-400";
  return (
    <motion.div
      variants={cardVariants(reduce)}
      whileHover={reduce ? undefined : { y: -2 }}
      transition={SPRING}
      className="group text-left neon-panel neon-panel-hover rounded-2xl p-4 hover:bg-bg-elev relative overflow-hidden"
    >
      <button type="button" onClick={() => onOpen(app.name)} className="absolute inset-0 z-0" aria-label={`Open ${app.name}`} />
      <span className="pointer-events-none absolute top-4 right-4 text-accent-soft opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 text-sm">→</span>
      <div className="pointer-events-none flex items-center gap-2">
        <span className={cn("w-2 h-2 rounded-full shrink-0", dot)} />
        <span className={cn("text-[15px] font-semibold tracking-tight truncate", !live && "text-zinc-500")}>{app.name}</span>
        <span className="text-[9.5px] font-semibold px-1.5 py-px rounded bg-accent/15 text-accent-soft shrink-0">{app.type}</span>
        {app.internet_exposed && (
          <span className="text-[9.5px] font-semibold px-1.5 py-px rounded bg-emerald-500/15 text-emerald-300 shrink-0">{app.cloudflare ? "CF" : "live"}</span>
        )}
      </div>
      {app.urls?.length > 0 ? (
        <div className="pointer-events-none text-[12px] text-zinc-500 mt-2 truncate">{app.urls[0].replace(/^https?:\/\//, "")}</div>
      ) : (
        <div className="pointer-events-none text-[12px] text-zinc-600 mt-2 truncate">{live ? "no public url" : "folder tracked only"}</div>
      )}
      <div className="pointer-events-none text-[12px] text-mono text-zinc-400 font-mono tabular-nums mt-2">
        {app.components_count ?? 0} comp
        <span className="text-zinc-700 mx-1.5">·</span>
        {app.listening_ports?.length || 0} ports
        <span className="text-zinc-700 mx-1.5">·</span>
        {formatBytes(app.total_size_bytes)}
      </div>
      <div className="pointer-events-none flex flex-wrap gap-1.5 mt-3">
        {app.containers?.length > 0 && <Chip icon={Container} n={app.containers.length} label="containers" />}
        {app.systemd_units?.length > 0 && <Chip icon={Cog} n={app.systemd_units.length} label="services" />}
        {app.nginx_sites?.length > 0 && <Chip icon={Globe} n={app.nginx_sites.length} label="nginx" />}
        {app.volumes?.length > 0 && <Chip icon={HardDrive} n={app.volumes.length} label="volumes" />}
        {app.images?.length > 0 && <Chip icon={Package} n={app.images.length} label="images" />}
      </div>
    <AppActionRow name={app.name} />
    </motion.div>
  );
}

function ProjectsLens({ apps, onOpen, reduce }) {
  const sorted = useMemo(
    () => [...apps].sort((a, b) => attentionScore(a) - attentionScore(b)),
    [apps]
  );
  return (
    <>
      <div className="flex items-baseline gap-3 mb-4">
        <h1 className="text-[21px] font-semibold tracking-tight">Projects</h1>
        <p className="text-[13px] text-zinc-500">
          One card per <span className="font-mono text-zinc-400">~/projects/&lt;name&gt;</span> — attention-sorted
        </p>
      </div>
      <motion.div
        variants={gridVariants(reduce)}
        initial="hidden"
        animate="show"
        className="grid gap-3"
        style={{ gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))" }}
      >
        {sorted.map((a) => (
          <ProjectLensCard key={a.application_id || a.name} app={a} onOpen={onOpen} reduce={reduce} />
        ))}
      </motion.div>
    </>
  );
}

function ServersLens({ apps, reduce }) {
  const liveCount = HOSTS.filter((h) => h.live).length;
  return (
    <>
      <div className="flex items-baseline gap-3 mb-4">
        <h1 className="text-[21px] font-semibold tracking-tight">Servers</h1>
        <p className="text-[13px] text-zinc-500">
          {liveCount} of {HOSTS.length} hosts reporting · Tailscale mesh
        </p>
      </div>
      <motion.div
        variants={gridVariants(reduce)}
        initial="hidden"
        animate="show"
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fill,minmax(340px,1fr))" }}
      >
        {HOSTS.map((h) => {
          const live = h.live;
          const exposed = live ? apps.filter((a) => a.internet_exposed).length : 0;
          const disk = live ? apps.reduce((s, a) => s + (a.total_size_bytes || 0), 0) : 0;
          return (
            <motion.div
              key={h.id}
              variants={cardVariants(reduce)}
              whileHover={reduce || !live ? undefined : { y: -2 }}
              transition={SPRING}
              className={cn(
                "rounded-2xl p-5",
                live ? "neon-panel neon-panel-hover" : "neon-dashed bg-bg-card/30"
              )}
            >
              <div className="flex items-center gap-2.5">
                <span className={cn("w-2.5 h-2.5 rounded-full shrink-0", live ? "bg-emerald-400" : "bg-zinc-600")} />
                <span className={cn("text-[16px] font-semibold tracking-tight", !live && "text-zinc-400")}>{h.name}</span>
                <span className={cn(
                  "text-[9.5px] font-semibold px-1.5 py-px rounded shrink-0",
                  live ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-700/40 text-zinc-400"
                )}>
                  {live ? "online" : "pending agent"}
                </span>
                <span className="ml-auto text-[10.5px] text-zinc-600 font-mono shrink-0">TS {h.ts}</span>
              </div>
              {h.note && <div className="text-[12px] text-zinc-500 mt-1.5">{h.note}</div>}

              {live ? (
                <div className="grid grid-cols-3 gap-3 mt-4">
                  <Fact k="apps" v={apps.length} />
                  <Fact k="exposed" v={exposed} tone={exposed ? "#00ED64" : undefined} />
                  <Fact k="disk" v={formatBytes(disk)} />
                  <Fact k="public ip" v={h.ip || "—"} mono />
                  <Fact k="shape" v="A1.Flex" mono />
                  <Fact k="region" v="ap-hyd-1" mono />
                </div>
              ) : (
                <div className="mt-4 flex items-center gap-2 text-[12px] text-zinc-500">
                  <span className="text-accent-cyan">◇</span>
                  Deploy the InfraDocs agent to claim this host.
                  <span className="text-zinc-600 ml-auto">Phase 6</span>
                </div>
              )}
            </motion.div>
          );
        })}
      </motion.div>
    </>
  );
}

function Fact({ k, v, mono, tone }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-600">{k}</div>
      <div
        className={cn("text-[13px] text-zinc-200 mt-0.5", mono && "font-mono")}
        style={tone ? { color: tone } : undefined}
      >
        {v}
      </div>
    </div>
  );
}

const SCOPE_STYLE = {
  public: "bg-emerald-500/15 text-emerald-300",
  tailnet: "bg-cyan-500/15 text-cyan-300",
  localhost: "bg-zinc-500/15 text-zinc-300",
  "all-interfaces": "bg-amber-500/15 text-amber-300",
  "private-lan": "bg-violet-500/15 text-violet-300",
  private: "bg-zinc-500/15 text-zinc-300",
};
const KIND_STYLE = {
  web: "bg-accent/15 text-accent-soft",
  database: "bg-rose-500/15 text-rose-300",
  monitoring: "bg-amber-500/15 text-amber-300",
  infra: "bg-zinc-500/15 text-zinc-400",
};

function AIControls() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["ai-status"], queryFn: () => endpoints.aiStatus().then((r) => r.data) });
  const insightsQ = useQuery({ queryKey: ["ai-insights"], queryFn: () => endpoints.getAiInsights().then((r) => r.data) });
  const [msg, setMsg] = useState("");
  const enrich = useMutation({
    mutationFn: () => endpoints.aiEnrich().then((r) => r.data),
    onSuccess: (d) => {
      setMsg(d.enabled ? `Labeling ${d.scheduled} unknown service(s) in the background…` : d.message);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["endpoints"] });
        qc.invalidateQueries({ queryKey: ["ai-status"] });
      }, 7000);
    },
  });
  const runInsights = useMutation({
    mutationFn: () => endpoints.runAiInsights().then((r) => r.data),
    onSuccess: () => insightsQ.refetch(),
  });
  if (!status.data) return null;
  const insights = insightsQ.data?.insights;
  const btn = "text-[12px] px-3 py-1.5 rounded-lg disabled:opacity-50 transition";
  return (
    <div className="mb-4">
      {!status.data.enabled ? (
        <div className="text-[12px] text-zinc-500">
          AI labeling off — add an OpenAI-compatible endpoint in Setup to auto-identify unknown services.
        </div>
      ) : (
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => enrich.mutate()} disabled={enrich.isPending}
            className={cn(btn, "neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20")}>
            {enrich.isPending ? "…" : "✨ Label unknowns (AI)"}
          </button>
          <button onClick={() => runInsights.mutate()} disabled={runInsights.isPending}
            className={cn(btn, "border border-white/10 hover:bg-bg-elev text-zinc-300")}>
            {runInsights.isPending ? "Analyzing…" : "🧠 Fleet insights"}
          </button>
          <span className="text-[11px] text-zinc-500">{status.data.labeled} AI-labeled · {status.data.model}</span>
          {msg && <span className="text-[11px] text-accent-soft">{msg}</span>}
        </div>
      )}
      {insights && (
        <div className="neon-panel rounded-xl p-4 mt-3 text-sm">
          <div className="text-zinc-200">{insights.summary}</div>
          {insights.observations?.length > 0 && (
            <ul className="list-disc pl-5 mt-2 space-y-1 text-[12.5px] text-zinc-400">
              {insights.observations.map((o, i) => <li key={i}>{o}</li>)}
            </ul>
          )}
          {insights.recommendations?.length > 0 && (
            <div className="mt-2 text-[12.5px]">
              <span className="text-amber-300">Recommendations:</span>
              <ul className="list-disc pl-5 mt-1 space-y-1 text-zinc-400">
                {insights.recommendations.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function WebLens() {
  const q = useQuery({
    queryKey: ["endpoints"],
    queryFn: () => endpoints.listEndpoints().then((r) => r.data),
  });
  const eps = q.data?.endpoints || [];
  return (
    <div>
      <div className="flex items-baseline gap-3 mb-1">
        <h1 className="text-[21px] font-semibold tracking-tight">Web &amp; Services</h1>
        <span className="text-[13px] text-zinc-500">{eps.length} reachable</span>
      </div>
      <p className="text-[13px] text-zinc-500 mb-4">
        Every hosted page / UI / service across the fleet — clickable, with where it
        lives and how it's reached.
      </p>
      <AIControls />
      {q.isLoading && <div className="text-zinc-400 text-sm">Loading…</div>}
      <div className="space-y-2">
        {eps.map((e, i) => (
          <div key={i} className="neon-panel rounded-xl px-4 py-3 flex items-start gap-3">
            <span className={cn("text-[10px] px-2 py-0.5 rounded-full shrink-0 mt-0.5 font-medium",
              KIND_STYLE[e.kind] || KIND_STYLE.infra)}>{e.kind}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {e.url ? (
                  <a href={e.url} target="_blank" rel="noreferrer"
                     className="text-accent-soft hover:underline font-medium font-mono text-[13px] truncate">
                    {e.url}
                  </a>
                ) : (
                  <span className="font-medium font-mono text-[13px] text-zinc-300">{e.host}</span>
                )}
                <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full shrink-0",
                  SCOPE_STYLE[e.scope] || SCOPE_STYLE.private)}>{e.scope}</span>
                {e.ai && <span className="text-[10px] px-1.5 py-0.5 rounded-full shrink-0 bg-[var(--neon)]/15 text-[var(--neon)]">AI</span>}
              </div>
              <div className="text-xs text-zinc-400 mt-1">
                <span className="text-zinc-200">{e.service}</span>
                {e.recognized && e.recognized !== e.service && <span className="text-zinc-500"> · {e.recognized}</span>}
                <span className="text-zinc-600"> · {e.server}</span>
                {e.via && <span className="text-zinc-600"> · via {e.via}</span>}
              </div>
              {e.purpose && <div className="text-[11px] text-[var(--neon)]/80 mt-1">{e.purpose}</div>}
              <div className="text-[11px] text-zinc-500 mt-1">{e.access}</div>
            </div>
          </div>
        ))}
        {!q.isLoading && eps.length === 0 && (
          <div className="text-sm text-zinc-500">No endpoints found yet — run a scan.</div>
        )}
      </div>
    </div>
  );
}

export default function LensHome() {
  const [params, setParams] = useSearchParams();
  const lens = LENSES.includes(params.get("lens")) ? params.get("lens") : "Dashboard";
  const setLens = (l) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (l === "Dashboard") next.delete("lens");
      else next.set("lens", l);
      return next;
    });
  const reduce = useReducedMotion();
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["applications"],
    queryFn: () => endpoints.listApplications().then((r) => r.data),
  });

  const all = q.data?.applications || [];
  const projects = all.filter((a) => a.type === "project");
  const open = (name) => navigate(`/applications?sel=${encodeURIComponent(name)}`);

  return (
    <div>
      <div className="flex gap-1.5 mb-6">
        {LENSES.map((l) => (
          <button
            key={l}
            onClick={() => (l === "Assets" ? navigate("/assets") : setLens(l))}
            className={cn(
              "px-3 py-1.5 rounded-lg text-[13px] font-medium border transition",
              lens === l
                ? "text-accent-soft bg-accent/10 border-accent/30"
                : "text-zinc-400 border-transparent hover:text-zinc-100 hover:bg-bg-elev"
            )}
          >
            {l}
          </button>
        ))}
      </div>

      {q.isLoading && (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))" }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[132px] rounded-2xl bg-bg-card border border-bg-hover skeleton-shimmer" />
          ))}
        </div>
      )}

      {!q.isLoading && (
        <AnimatePresence mode="wait">
          <motion.div
            key={lens}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: 0.16 }}
          >
            {lens === "Projects" && <ProjectsLens apps={projects} onOpen={open} reduce={reduce} />}
            {lens === "Servers" && <ServersLens apps={all} reduce={reduce} />}
            {lens === "Web" && <WebLens />}
            {lens === "Dashboard" && <Dashboard />}
            {lens === "Assets" && (
              <div className="flex items-baseline gap-3 mb-4">
                <h1 className="text-[21px] font-semibold tracking-tight">Assets</h1>
                <p className="text-[13px] text-zinc-500">
                  Open the <button onClick={() => navigate("/assets")} className="text-accent-soft hover:underline">full asset table →</button>
                </p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
