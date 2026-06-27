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

// A secondary is considered stale if it hasn't pushed within this window.
const SERVER_STALE_MS = 15 * 60 * 1000;

// application_id is `${server_id}:app:${name}` — recover the owning server.
function serverOfApp(a) {
  const id = a.application_id || "";
  const i = id.indexOf(":app:");
  return i > 0 ? id.slice(0, i) : null;
}

function relTime(iso) {
  if (!iso) return "never";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "unknown";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

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

// Switcher chip — scopes the fleet view to one server (or All).
function SwitchChip({ active, onClick, label, dot }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "px-3 py-1.5 rounded-lg text-[12px] font-medium border transition inline-flex items-center gap-1.5",
        active
          ? "text-accent-soft bg-accent/10 border-accent/30"
          : "text-zinc-400 border-transparent hover:text-zinc-100 hover:bg-bg-elev"
      )}
    >
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full", dot)} />}
      {label}
    </button>
  );
}

function ServerCard({ s, reduce, onOpen }) {
  return (
    <motion.div
      variants={cardVariants(reduce)}
      whileHover={reduce ? undefined : { y: -2 }}
      transition={SPRING}
      onClick={onOpen}
      className={cn(
        "rounded-2xl p-5 cursor-pointer",
        s.online ? "neon-panel neon-panel-hover" : "neon-dashed bg-bg-card/30"
      )}
    >
      <div className="flex items-center gap-2.5">
        <span className={cn("w-2.5 h-2.5 rounded-full shrink-0", s.online ? "bg-emerald-400" : "bg-zinc-600")} />
        <span className={cn("text-[16px] font-semibold tracking-tight", !s.online && "text-zinc-400")}>{s.name}</span>
        <span className={cn(
          "text-[9.5px] font-semibold px-1.5 py-px rounded shrink-0",
          s.role === "primary" ? "bg-accent/15 text-accent-soft" : "bg-zinc-700/40 text-zinc-300"
        )}>
          {s.role}
        </span>
        <span className={cn(
          "text-[9.5px] font-semibold px-1.5 py-px rounded shrink-0",
          s.online ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-700/40 text-zinc-400"
        )}>
          {s.online ? "online" : "stale"}
        </span>
        <span className="ml-auto text-[10.5px] text-zinc-600 font-mono shrink-0">
          {s.role === "primary" ? "this host" : relTime(s.lastSeen)}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3 mt-4">
        <Fact k="apps" v={s.apps} />
        {s.role === "primary" ? (
          <Fact k="exposed" v={s.exposed} tone={s.exposed ? "#00ED64" : undefined} />
        ) : (
          <Fact k="assets" v={s.assets} />
        )}
        <Fact k="role" v={s.role} mono />
      </div>
    </motion.div>
  );
}

// "Add a server" — mints a join token, then shows the operator exactly how to
// enroll the secondary (it pushes outbound to this primary, so NAT-friendly).
function AddServerPanel({ qc }) {
  const [serverId, setServerId] = useState("");
  const [minted, setMinted] = useState(null);
  const mint = useMutation({
    mutationFn: (id) => endpoints.mintFederationToken(id).then((r) => r.data),
    onSuccess: (d) => {
      setMinted(d);
      qc.invalidateQueries({ queryKey: ["federation-servers"] });
    },
  });
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return (
    <div className="neon-panel rounded-xl p-4 mb-4">
      <div className="text-[13px] text-zinc-200 mb-1 font-medium">Add a secondary server</div>
      <p className="text-[12px] text-zinc-500 mb-3">
        Mint a join token below, then on the new host run the InfraDocs setup wizard,
        choose role <span className="font-mono text-zinc-400">secondary</span>, and enter this
        primary's URL + the token. The secondary scans itself and pushes{" "}
        <span className="font-mono text-zinc-400">outbound</span> to this primary — no inbound
        ports required.
      </p>
      <div className="flex gap-2 items-center flex-wrap">
        <input
          value={serverId}
          onChange={(e) => setServerId(e.target.value)}
          placeholder="server id (e.g. n150)"
          className="bg-bg-elev border border-bg-hover rounded-lg px-3 py-1.5 text-[13px] text-zinc-200 font-mono focus:outline-none focus:border-accent/40"
        />
        <button
          onClick={() => mint.mutate(serverId.trim())}
          disabled={!serverId.trim() || mint.isPending}
          className="text-[12px] px-3 py-1.5 rounded-lg disabled:opacity-50 neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20"
        >
          {mint.isPending ? "Minting…" : "Mint join token"}
        </button>
      </div>
      {mint.isError && (
        <div className="text-[12px] text-rose-300 mt-2">Failed to mint token — check you're signed in as the primary.</div>
      )}
      {minted && (
        <div className="mt-3 text-[12px]">
          <div className="text-zinc-400 mb-1">
            Join token for <span className="font-mono text-accent-soft">{minted.server_id}</span> — copy it now (shown once):
          </div>
          <div className="bg-black/40 border border-bg-hover rounded-lg p-3 font-mono text-[11.5px] text-zinc-200 break-all flex items-start gap-2">
            <span className="flex-1">{minted.token}</span>
            <button
              onClick={() => navigator.clipboard?.writeText(minted.token)}
              className="text-accent-soft hover:underline shrink-0"
            >
              copy
            </button>
          </div>
          <div className="text-zinc-500 mt-2">
            Primary URL for the wizard: <span className="font-mono text-zinc-300">{origin}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// Actions a remote secondary can run (subset of the local allow-list that's
// safe to drive from a free-text asset id — read/lifecycle verbs).
const REMOTE_ACTIONS = ["restart", "start", "stop", "logs", "status"];

function CmdStatusBadge({ status }) {
  const tone =
    {
      pending: "bg-amber-500/15 text-amber-300",
      dispatched: "bg-sky-500/15 text-sky-300",
      success: "bg-emerald-500/15 text-emerald-300",
      failed: "bg-rose-500/15 text-rose-300",
      refused: "bg-zinc-700/40 text-zinc-300",
    }[status] || "bg-zinc-700/40 text-zinc-300";
  return <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full shrink-0", tone)}>{status}</span>;
}

// Minimal dispatch affordance: queue an action for a secondary and watch it
// run. Commands complete asynchronously (the secondary polls), so the list
// auto-refreshes until results land.
function RemoteActionsPanel({ serverId }) {
  const qc = useQueryClient();
  const [assetId, setAssetId] = useState("");
  const [action, setAction] = useState("restart");
  const cmds = useQuery({
    queryKey: ["fed-commands", serverId],
    queryFn: () => endpoints.listFederationCommands(serverId).then((r) => r.data),
    refetchInterval: 4000,
  });
  const dispatch = useMutation({
    mutationFn: () =>
      endpoints.dispatchFederationCommand(serverId, assetId.trim(), action).then((r) => r.data),
    onSuccess: () => {
      setAssetId("");
      qc.invalidateQueries({ queryKey: ["fed-commands", serverId] });
    },
  });
  const rows = cmds.data?.commands || [];
  return (
    <div className="neon-panel rounded-xl p-4 mt-4">
      <div className="text-[13px] text-zinc-200 mb-1 font-medium">Remote actions · {serverId}</div>
      <p className="text-[12px] text-zinc-500 mb-3">
        Queue an action for this secondary. It runs on the secondary's next poll
        (outbound, NAT-friendly) through the same guarded dispatcher as local actions
        — <span className="font-mono text-zinc-400">infradocs-v6-*</span> units are refused — then
        reports back, fully audited.
      </p>
      <div className="flex gap-2 items-center flex-wrap mb-3">
        <input
          value={assetId}
          onChange={(e) => setAssetId(e.target.value)}
          placeholder="asset id (from the Assets table)"
          className="bg-bg-elev border border-bg-hover rounded-lg px-3 py-1.5 text-[13px] text-zinc-200 font-mono focus:outline-none focus:border-accent/40 flex-1 min-w-[220px]"
        />
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="bg-bg-elev border border-bg-hover rounded-lg px-3 py-1.5 text-[13px] text-zinc-200"
        >
          {REMOTE_ACTIONS.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <button
          onClick={() => dispatch.mutate()}
          disabled={!assetId.trim() || dispatch.isPending}
          className="text-[12px] px-3 py-1.5 rounded-lg disabled:opacity-50 neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20"
        >
          {dispatch.isPending ? "Dispatching…" : "Dispatch"}
        </button>
      </div>
      {dispatch.isError && (
        <div className="text-[12px] text-rose-300 mb-2">
          {dispatch.error?.response?.data?.detail || "dispatch failed"}
        </div>
      )}
      <div className="space-y-1.5">
        {rows.length === 0 && <div className="text-[12px] text-zinc-500">No commands dispatched yet.</div>}
        {rows.map((c) => (
          <div key={c.command_id} className="bg-black/30 border border-bg-hover rounded-lg px-3 py-2 text-[12px]">
            <div className="flex items-center gap-2">
              <span className="font-mono text-zinc-200">{c.action}</span>
              <span className="text-zinc-500 font-mono truncate">{c.asset?.name || c.asset?.asset_id}</span>
              <CmdStatusBadge status={c.status} />
              <span className="ml-auto text-zinc-600 font-mono text-[10.5px]">{relTime(c.created_at)}</span>
            </div>
            {c.result?.stdout && (
              <pre className="text-[11px] text-zinc-400 mt-1 whitespace-pre-wrap break-all max-h-24 overflow-auto">
                {c.result.stdout.slice(0, 600)}
              </pre>
            )}
            {c.result?.stderr && (
              <pre className="text-[11px] text-rose-300/80 mt-1 whitespace-pre-wrap break-all max-h-24 overflow-auto">
                {c.result.stderr.slice(0, 600)}
              </pre>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ServersLens({ apps, reduce, selected, setSelected }) {
  const qc = useQueryClient();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => endpoints.health().then((r) => r.data),
  });
  const fed = useQuery({
    queryKey: ["federation-servers"],
    queryFn: () => endpoints.federationServers().then((r) => r.data),
  });
  const [adding, setAdding] = useState(false);

  const primaryId = health.data?.server;
  const secondaries = fed.data?.servers || [];

  const servers = useMemo(() => {
    const list = [];
    if (primaryId) {
      const own = apps.filter((a) => serverOfApp(a) === primaryId);
      list.push({
        id: primaryId,
        name: health.data?.server_name || primaryId,
        role: "primary",
        online: health.data?.status === "ok",
        apps: own.length,
        exposed: own.filter((a) => a.internet_exposed).length,
        assets: null,
        lastSeen: null,
      });
    }
    for (const s of secondaries) {
      if (s.server_id === primaryId) continue; // never double-list the primary
      const online = s.last_seen
        ? Date.now() - new Date(s.last_seen).getTime() < SERVER_STALE_MS
        : false;
      list.push({
        id: s.server_id,
        name: s.server_id,
        role: "secondary",
        online,
        apps: s.app_count ?? 0,
        assets: s.asset_count ?? 0,
        exposed: null,
        lastSeen: s.last_seen,
      });
    }
    return list;
  }, [apps, primaryId, secondaries, health.data]);

  const shown = selected ? servers.filter((s) => s.id === selected) : servers;
  const onlineCount = servers.filter((s) => s.online).length;
  const loading = health.isLoading || fed.isLoading;

  return (
    <>
      <div className="flex items-baseline gap-3 mb-4 flex-wrap">
        <h1 className="text-[21px] font-semibold tracking-tight">Servers</h1>
        <p className="text-[13px] text-zinc-500">
          {onlineCount} of {servers.length} reporting · federation mesh
        </p>
        <button
          onClick={() => setAdding((v) => !v)}
          className="ml-auto text-[12px] px-3 py-1.5 rounded-lg neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20"
        >
          {adding ? "× Close" : "+ Add a server"}
        </button>
      </div>

      {adding && <AddServerPanel qc={qc} />}

      {servers.length > 0 && (
        <div className="flex gap-1.5 mb-4 flex-wrap">
          <SwitchChip active={!selected} onClick={() => setSelected("")} label={`All (${servers.length})`} />
          {servers.map((s) => (
            <SwitchChip
              key={s.id}
              active={selected === s.id}
              onClick={() => setSelected(s.id)}
              label={s.name}
              dot={s.online ? "bg-emerald-400" : "bg-zinc-600"}
            />
          ))}
        </div>
      )}

      {loading && <div className="text-zinc-400 text-sm">Loading fleet…</div>}

      <motion.div
        variants={gridVariants(reduce)}
        initial="hidden"
        animate="show"
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fill,minmax(340px,1fr))" }}
      >
        {shown.map((s) => (
          <ServerCard key={s.id} s={s} reduce={reduce} onOpen={() => setSelected(s.id)} />
        ))}
      </motion.div>

      {selected && servers.find((s) => s.id === selected)?.role === "secondary" && (
        <RemoteActionsPanel serverId={selected} />
      )}

      {!loading && servers.length === 0 && (
        <div className="text-sm text-zinc-500">
          No servers reporting yet. Use “Add a server” to enroll a secondary.
        </div>
      )}
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
  const selectedServer = params.get("server") || "";
  const setSelectedServer = (id) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (!id) next.delete("server");
      else next.set("server", id);
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
            {lens === "Servers" && (
              <ServersLens apps={all} reduce={reduce} selected={selectedServer} setSelected={setSelectedServer} />
            )}
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
