import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Container, Cog, Globe, HardDrive, Package } from "lucide-react";
import { endpoints } from "../api/client";
import { formatBytes } from "../components/Bytes";
import { cn } from "../lib/cn";
import Dashboard from "./Dashboard";

const LENSES = ["Dashboard", "Projects", "Servers", "Resources", "Assets"];

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

function ProjectLensCard({ app, onOpen }) {
  const live = hasRuntime(app);
  const dot = !live ? "bg-zinc-600" : app.internet_exposed ? "bg-emerald-400" : "bg-sky-400";
  return (
    <button
      onClick={() => onOpen(app.name)}
      className="group text-left bg-bg-card border border-bg-hover rounded-2xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:bg-bg-elev hover:border-zinc-700 relative overflow-hidden"
    >
      <span className="absolute top-4 right-4 text-accent-soft opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 text-sm">→</span>
      <div className="flex items-center gap-2">
        <span className={cn("w-2 h-2 rounded-full shrink-0", dot)} />
        <span className={cn("text-[15px] font-semibold tracking-tight truncate", !live && "text-zinc-500")}>{app.name}</span>
        <span className="text-[9.5px] font-semibold px-1.5 py-px rounded bg-accent/15 text-accent-soft shrink-0">{app.type}</span>
        {app.internet_exposed && (
          <span className="text-[9.5px] font-semibold px-1.5 py-px rounded bg-emerald-500/15 text-emerald-300 shrink-0">{app.cloudflare ? "CF" : "live"}</span>
        )}
      </div>
      {app.urls?.length > 0 ? (
        <div className="text-[12px] text-zinc-500 mt-2 truncate">{app.urls[0].replace(/^https?:\/\//, "")}</div>
      ) : (
        <div className="text-[12px] text-zinc-600 mt-2 truncate">{live ? "no public url" : "folder tracked only"}</div>
      )}
      <div className="text-[12px] text-mono text-zinc-400 font-mono tabular-nums mt-2">
        {app.components_count ?? 0} comp
        <span className="text-zinc-700 mx-1.5">·</span>
        {app.listening_ports?.length || 0} ports
        <span className="text-zinc-700 mx-1.5">·</span>
        {formatBytes(app.total_size_bytes)}
      </div>
      <div className="flex flex-wrap gap-1.5 mt-3">
        {app.containers?.length > 0 && <Chip icon={Container} n={app.containers.length} label="containers" />}
        {app.systemd_units?.length > 0 && <Chip icon={Cog} n={app.systemd_units.length} label="services" />}
        {app.nginx_sites?.length > 0 && <Chip icon={Globe} n={app.nginx_sites.length} label="nginx" />}
        {app.volumes?.length > 0 && <Chip icon={HardDrive} n={app.volumes.length} label="volumes" />}
        {app.images?.length > 0 && <Chip icon={Package} n={app.images.length} label="images" />}
      </div>
    </button>
  );
}

function ProjectsLens({ apps, onOpen }) {
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
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))" }}>
        {sorted.map((a) => (
          <ProjectLensCard key={a.application_id || a.name} app={a} onOpen={onOpen} />
        ))}
      </div>
    </>
  );
}

function ServersLens({ apps }) {
  return (
    <>
      <div className="flex items-baseline gap-3 mb-4">
        <h1 className="text-[21px] font-semibold tracking-tight">Servers</h1>
        <p className="text-[13px] text-zinc-500">Hosts in the Tailscale mesh — substrate facts per host</p>
      </div>
      <div className="space-y-5">
        {HOSTS.map((h) => (
          <div key={h.id}>
            <div className="flex items-center gap-2.5 mb-2.5">
              <span className={cn("w-2 h-2 rounded-full", h.live ? "bg-emerald-400" : "bg-zinc-600")} />
              <span className="text-[15px] font-semibold">{h.name}</span>
              <span className="text-[11px] text-zinc-600 font-mono">
                {h.ip ? `${h.ip} · ` : ""}TS {h.ts}
              </span>
            </div>
            {h.live ? (
              <div className="bg-bg-card border border-bg-hover rounded-2xl p-4">
                <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))" }}>
                  <Fact k="apps" v={apps.length} />
                  <Fact k="exposed" v={apps.filter((a) => a.internet_exposed).length} />
                  <Fact k="disk" v={formatBytes(apps.reduce((s, a) => s + (a.total_size_bytes || 0), 0))} />
                  <Fact k="shape" v="A1.Flex" mono />
                  <Fact k="region" v="ap-hyderabad-1" mono />
                </div>
              </div>
            ) : (
              <div className="bg-bg-card border border-dashed border-bg-hover rounded-2xl p-4 text-[13px] text-zinc-500">
                ◇ no agent yet{h.note ? ` — ${h.note}` : ""} <span className="text-zinc-600">(Phase 6)</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function Fact({ k, v, mono }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-600">{k}</div>
      <div className={cn("text-[13px] text-zinc-200 mt-0.5", mono && "font-mono")}>{v}</div>
    </div>
  );
}

export default function LensHome() {
  const [lens, setLens] = useState("Dashboard");
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ["applications"],
    queryFn: () => endpoints.listApplications().then((r) => r.data),
  });

  const all = q.data?.applications || [];
  const projects = all.filter((a) => a.type === "project");
  const open = (name) => navigate(`/applications/${encodeURIComponent(name)}`);

  return (
    <div>
      <div className="flex gap-1.5 mb-6">
        {LENSES.map((l) => (
          <button
            key={l}
            onClick={() => setLens(l)}
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
            <div key={i} className="h-[132px] rounded-2xl bg-bg-card border border-bg-hover animate-pulse" />
          ))}
        </div>
      )}

      {!q.isLoading && lens === "Projects" && <ProjectsLens apps={projects} onOpen={open} />}
      {!q.isLoading && lens === "Servers" && <ServersLens apps={all} />}
      {lens === "Dashboard" && <Dashboard />}
      {lens === "Resources" && <Dashboard />}
      {lens === "Assets" && (
        <div className="flex items-baseline gap-3 mb-4">
          <h1 className="text-[21px] font-semibold tracking-tight">Assets</h1>
          <p className="text-[13px] text-zinc-500">
            Open the <button onClick={() => navigate("/assets")} className="text-accent-soft hover:underline">full asset table →</button>
          </p>
        </div>
      )}
    </div>
  );
}
