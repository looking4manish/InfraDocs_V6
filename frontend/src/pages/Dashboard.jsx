import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  LabelList,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  AppWindow,
  Globe,
  Layers,
  Network,
  HardDrive,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import { endpoints } from "../api/client";
import { formatBytes } from "../components/Bytes";
import StatePill from "../components/StatePill";
import { cn } from "../lib/cn";

// Mockup palette (violet primary, then teal/amber/blue/coral), extended for
// charts with many slices/bars. Status colours stay reserved for StatePill.
const PALETTE = [
  "#7c6ee6",
  "#3aa389",
  "#c79a4b",
  "#5b8fd0",
  "#c4684d",
  "#9d8df1",
  "#4fb8ab",
  "#c97fa6",
  "#8fae5a",
  "#c98262",
];

function relTime(ts) {
  if (!ts) return "—";
  const s = (Date.now() - new Date(ts).getTime()) / 1000;
  if (s < 60) return `${Math.max(0, Math.floor(s))}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

// ----- shared chrome -------------------------------------------------------

function ChartTip({ active, payload, nameKey, valueFmt }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload || {};
  const name = nameKey ? row[nameKey] : payload[0].name;
  const value = payload[0].value;
  return (
    <div className="rounded-md border border-bg-hover bg-bg-elev px-2.5 py-1.5 text-xs shadow-xl">
      <div className="text-zinc-300">{String(name ?? "").replace(/_/g, " ")}</div>
      <div className="font-mono tabular-nums text-zinc-100">
        {valueFmt ? valueFmt(value) : value}
      </div>
    </div>
  );
}

function Panel({ title, to, linkLabel = "View all", children, className }) {
  return (
    <div
      className={cn(
        "neon-panel rounded-2xl p-5",
        className
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-zinc-200">{title}</h2>
        {to && (
          <Link
            to={to}
            className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-accent transition"
          >
            {linkLabel} <ArrowRight size={13} />
          </Link>
        )}
      </div>
      {children}
    </div>
  );
}

function Kpi({ icon: Icon, label, value, sub, to, tone = "#00ED64" }) {
  return (
    <Link
      to={to}
      className="group neon-panel neon-panel-hover rounded-2xl p-4 hover:bg-bg-elev transition flex items-start gap-3"
    >
      <span
        className="w-10 h-10 rounded-xl grid place-items-center shrink-0"
        style={{ backgroundColor: tone + "1f", color: tone }}
      >
        <Icon size={18} />
      </span>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide text-zinc-400">
          {label}
        </div>
        <div className="text-2xl font-semibold text-zinc-100 leading-tight mt-0.5 tabular-nums">
          {value}
        </div>
        {sub && <div className="text-[11px] text-zinc-400 mt-0.5 truncate">{sub}</div>}
      </div>
    </Link>
  );
}

function DonutPanel({
  title,
  to,
  linkLabel,
  data,
  nameKey,
  valueKey,
  centerValue,
  centerLabel,
  valueFmt,
  footer,
  loading,
}) {
  return (
    <Panel title={title} to={to} linkLabel={linkLabel}>
      {loading ? (
        <div className="h-[150px] grid place-items-center text-sm text-zinc-400">
          Loading…
        </div>
      ) : (
        <>
          <div className="flex items-center gap-4">
            <div className="relative shrink-0" style={{ width: 150, height: 150 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey={valueKey}
                    nameKey={nameKey}
                    innerRadius={48}
                    outerRadius={70}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {data.map((_, i) => (
                      <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    content={<ChartTip nameKey={nameKey} valueFmt={valueFmt} />}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 grid place-items-center pointer-events-none">
                <div className="text-center">
                  <div className="text-lg font-semibold text-zinc-100 tabular-nums">
                    {centerValue}
                  </div>
                  <div className="text-[10px] uppercase tracking-wide text-zinc-400">
                    {centerLabel}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex-1 min-w-0 space-y-1.5">
              {data.slice(0, 6).map((d, i) => (
                <div key={d[nameKey]} className="flex items-center gap-2 text-xs">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: PALETTE[i % PALETTE.length] }}
                  />
                  <span className="text-zinc-400 truncate flex-1">
                    {String(d[nameKey]).replace(/_/g, " ")}
                  </span>
                  <span className="text-zinc-300 font-mono tabular-nums shrink-0">
                    {valueFmt ? valueFmt(d[valueKey]) : d[valueKey]}
                  </span>
                </div>
              ))}
            </div>
          </div>
          {footer}
        </>
      )}
    </Panel>
  );
}

// ----- page ----------------------------------------------------------------

export default function Dashboard() {
  const apps = useQuery({
    queryKey: ["applications"],
    queryFn: () => endpoints.listApplications().then((r) => r.data),
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => endpoints.assetCategories().then((r) => r.data.categories),
  });
  const ports = useQuery({
    queryKey: ["ports-summary"],
    queryFn: () => endpoints.portsSummary().then((r) => r.data),
  });
  const storage = useQuery({
    queryKey: ["storage-summary"],
    queryFn: () => endpoints.storageSummary().then((r) => r.data),
  });
  const scans = useQuery({
    queryKey: ["scans"],
    queryFn: () => endpoints.listScans(5).then((r) => r.data),
    refetchInterval: 3000,
  });
  const recentActions = useQuery({
    queryKey: ["actions-recent"],
    queryFn: () => endpoints.listActions({ limit: 6 }).then((r) => r.data),
    refetchInterval: 5000,
  });

  const appList = apps.data?.applications || [];
  const cats = categories.data || [];
  const totalAssets = cats.reduce((s, c) => s + (c.count || 0), 0);
  const lastScan = scans.data?.scans?.[0];
  const exposed = appList.filter((a) => a.internet_exposed);
  const cfCount = exposed.filter((a) => a.cloudflare).length;
  const projectAppCount = appList.filter((a) => a.type === "project").length;

  const storageByOwner = storage.data?.by_owner || [];
  const totalStorageBytes = storageByOwner.reduce(
    (s, o) => s + (o.size_bytes || 0),
    0
  );
  const portsByOwner = ports.data?.by_owner || [];
  const portsInUse = ports.data?.by_state?.in_use ?? 0;
  const portsDeclared = ports.data?.by_state?.declared ?? 0;

  const sortedCats = [...cats].sort((a, b) => b.count - a.count).slice(0, 8);
  const catChartHeight = Math.max(150, sortedCats.length * 28);
  const maxAppBytes = Math.max(1, ...appList.map((a) => a.total_size_bytes || 0));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Dashboard</h1>
        <p className="text-sm text-zinc-400 mt-0.5">
          {lastScan
            ? `Last scan ${relTime(lastScan.started_at)} · ${
                lastScan.total_assets ?? "—"
              } assets`
            : "Awaiting first scan"}
        </p>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Kpi
          icon={AppWindow}
          tone="#00ED64"
          label="Applications"
          value={apps.data?.count ?? "—"}
          sub={`${projectAppCount} projects · System`}
          to="/applications"
        />
        <Kpi
          icon={Globe}
          tone="#1D9E75"
          label="Exposed"
          value={exposed.length}
          sub={cfCount ? `${cfCount} via Cloudflare` : "via nginx"}
          to="/applications"
        />
        <Kpi
          icon={Layers}
          tone="#34d8e8"
          label="Assets"
          value={totalAssets || "—"}
          sub={`${cats.length} categories`}
          to="/assets"
        />
        <Kpi
          icon={Network}
          tone="#EF9F27"
          label="Ports"
          value={ports.data?.total ?? "—"}
          sub={`${portsInUse} in use`}
          to="/ports"
        />
        <Kpi
          icon={HardDrive}
          tone="#D85A30"
          label="Storage"
          value={formatBytes(totalStorageBytes)}
          sub={`${storage.data?.total ?? 0} entities`}
          to="/storage"
        />
        <Kpi
          icon={RefreshCw}
          tone={lastScan?.status === "failed" ? "#ef4444" : "#1D9E75"}
          label="Last scan"
          value={lastScan?.total_assets ?? "—"}
          sub={
            lastScan ? (
              <span className="inline-flex items-center gap-1.5">
                <StatePill value={lastScan.status} />
                {relTime(lastScan.started_at)}
              </span>
            ) : null
          }
          to="/scans"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <DonutPanel
          title="Storage by project"
          to="/storage"
          linkLabel="Details"
          loading={storage.isLoading}
          data={storageByOwner}
          nameKey="project"
          valueKey="size_bytes"
          valueFmt={formatBytes}
          centerValue={formatBytes(totalStorageBytes)}
          centerLabel="tracked"
        />

        <DonutPanel
          title="Ports by project"
          to="/ports"
          linkLabel="Details"
          loading={ports.isLoading}
          data={portsByOwner}
          nameKey="project"
          valueKey="count"
          centerValue={ports.data?.total ?? "—"}
          centerLabel="ports"
          footer={
            <div className="flex items-center gap-3 mt-3 pt-3 border-t border-bg-hover/60 text-xs">
              <span className="inline-flex items-center gap-1.5 text-emerald-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                {portsInUse} in use
              </span>
              <span className="inline-flex items-center gap-1.5 text-amber-300">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                {portsDeclared} declared
              </span>
            </div>
          }
        />

        <Panel title="Assets by category" to="/assets" linkLabel="Browse">
          {categories.isLoading ? (
            <div className="h-[150px] grid place-items-center text-sm text-zinc-400">
              Loading…
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={catChartHeight}>
              <BarChart
                data={sortedCats}
                layout="vertical"
                margin={{ top: 0, right: 28, left: 0, bottom: 0 }}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="category"
                  width={108}
                  tick={{ fill: "#d4d4d8", fontSize: 11 }}
                  tickFormatter={(s) => s.replace(/_/g, " ")}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "#26262b66" }}
                  content={<ChartTip nameKey="category" />}
                />
                <Bar dataKey="count" radius={[0, 5, 5, 0]} barSize={15}>
                  {sortedCats.map((_, i) => (
                    <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
                  ))}
                  <LabelList
                    dataKey="count"
                    position="right"
                    fill="#d4d4d8"
                    fontSize={11}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      {/* Lists row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Panel
          title="Applications"
          to="/applications"
          className="lg:col-span-2"
        >
          {apps.isLoading && (
            <div className="text-sm text-zinc-400">Loading…</div>
          )}
          <div className="divide-y divide-bg-hover/50">
            {appList.map((a) => {
              const hasRuntime =
                (a.components_count ?? 0) > 0 || a.internet_exposed;
              const pct = Math.round(
                ((a.total_size_bytes || 0) / maxAppBytes) * 100
              );
              return (
                <Link
                  key={a.application_id || a.name}
                  to={`/applications/${encodeURIComponent(a.name)}`}
                  className="block py-2.5 px-2 -mx-2 rounded-lg hover:bg-bg-hover/40 transition"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full shrink-0",
                        hasRuntime ? "bg-emerald-400" : "bg-zinc-600"
                      )}
                    />
                    <span className="text-sm font-medium text-zinc-200 truncate">
                      {a.name}
                    </span>
                    <span
                      className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded-full shrink-0",
                        a.type === "system"
                          ? "bg-slate-500/20 text-slate-300"
                          : "bg-accent/15 text-accent"
                      )}
                    >
                      {a.type}
                    </span>
                    {a.internet_exposed && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 shrink-0">
                        {a.cloudflare ? "CF" : "live"}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-zinc-400 font-mono tabular-nums shrink-0">
                      {a.components_count ?? 0} comp · {formatBytes(a.total_size_bytes)}
                    </span>
                  </div>
                  <div className="mt-1.5 h-1 rounded-full bg-bg-hover/60 overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${pct}%`, backgroundColor: "#7F77DD" }}
                    />
                  </div>
                </Link>
              );
            })}
          </div>
        </Panel>

        <Panel title="Recent actions" to="/actions" linkLabel="View log">
          {recentActions.isLoading && (
            <div className="text-sm text-zinc-400">Loading…</div>
          )}
          {recentActions.data?.count === 0 && (
            <div className="text-sm text-zinc-400">
              No actions yet. Fire one from an app or asset detail view.
            </div>
          )}
          <div className="space-y-3">
            {recentActions.data?.actions?.map((a) => (
              <div key={a._id} className="flex items-start gap-2.5">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 bg-accent" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-zinc-200 truncate">
                      {a.action}
                    </span>
                    <StatePill value={a.status} />
                  </div>
                  <div
                    className="text-[11px] text-zinc-400 truncate"
                    title={a.asset_id}
                  >
                    {a.asset_name}
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5">
                    {a.actor} ·{" "}
                    {a.timestamp ? new Date(a.timestamp).toLocaleString() : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
