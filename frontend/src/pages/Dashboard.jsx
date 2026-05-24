import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { endpoints } from "../api/client";
import { formatBytes } from "../components/Bytes";
import StatePill from "../components/StatePill";

function StatCard({ label, value, sub, to }) {
  const inner = (
    <div className="bg-bg-card border border-bg-hover rounded-lg p-4 hover:border-accent transition h-full">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}

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
    queryFn: () => endpoints.listActions({ limit: 5 }).then((r) => r.data),
    refetchInterval: 5000,
  });

  const totalAssets =
    (categories.data || []).reduce((sum, c) => sum + c.count, 0) || 0;
  const lastScan = scans.data?.scans?.[0];
  const exposedCount =
    (apps.data?.applications || []).filter((a) => a.internet_exposed).length;
  const projectAppCount =
    (apps.data?.applications || []).filter((a) => a.type === "project").length;

  const totalStorageBytes =
    (storage.data?.by_kind || []).reduce(
      (s, k) => s + (k.size_bytes || 0),
      0
    );

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Dashboard</h1>

      {/* Hero stats — all clickable, drill into the matching page */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <StatCard
          label="Applications"
          value={apps.data?.count ?? "—"}
          sub={`${projectAppCount} projects + System`}
          to="/applications"
        />
        <StatCard
          label="Internet-exposed"
          value={exposedCount}
          sub="via nginx"
          to="/applications"
        />
        <StatCard
          label="Total assets"
          value={totalAssets}
          to="/assets"
        />
        <StatCard
          label="Ports"
          value={ports.data?.total ?? "—"}
          sub={`${ports.data?.by_state?.in_use ?? 0} in use`}
          to="/ports"
        />
        <StatCard
          label="Storage tracked"
          value={formatBytes(totalStorageBytes)}
          sub={`${storage.data?.total ?? 0} entities`}
          to="/storage"
        />
        <StatCard
          label="Last scan"
          value={
            lastScan?.status ? (
              <span className="inline-flex items-center gap-2">
                <StatePill value={lastScan.status} />
              </span>
            ) : "—"
          }
          sub={
            lastScan?.started_at
              ? `${lastScan.total_assets ?? "—"} assets · ${new Date(
                  lastScan.started_at
                ).toLocaleString()}`
              : null
          }
          to="/scans"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Applications list — Phase 5+ correlated docs */}
        <div className="bg-bg-card border border-bg-hover rounded-lg p-4 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Applications</h2>
            <Link
              to="/applications"
              className="text-xs text-slate-400 hover:text-accent"
            >
              View all →
            </Link>
          </div>
          {apps.isLoading && (
            <div className="text-sm text-slate-400">Loading…</div>
          )}
          <div className="divide-y divide-bg-hover/40">
            {apps.data?.applications?.map((a) => (
              <Link
                key={a.application_id || a.name}
                to={`/applications/${encodeURIComponent(a.name)}`}
                className="flex items-center justify-between py-2 hover:bg-bg-hover/30 -mx-2 px-2 rounded text-sm"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="truncate">{a.name}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${
                      a.type === "system"
                        ? "bg-slate-500/20 text-slate-300"
                        : "bg-accent/15 text-accent"
                    }`}
                  >
                    {a.type}
                  </span>
                  {a.internet_exposed && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">
                      live
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-400 shrink-0">
                  <span>{a.components_count ?? 0} comp</span>
                  <span>{formatBytes(a.total_size_bytes)}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* Recent actions — Phase 8 audit feed */}
        <div className="bg-bg-card border border-bg-hover rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">Recent actions</h2>
            <Link to="/actions" className="text-xs text-slate-400 hover:text-accent">
              View log →
            </Link>
          </div>
          {recentActions.isLoading && (
            <div className="text-sm text-slate-400">Loading…</div>
          )}
          {recentActions.data?.count === 0 && (
            <div className="text-sm text-slate-500">
              No actions yet. Use the buttons in app/asset detail views.
            </div>
          )}
          <div className="space-y-2">
            {recentActions.data?.actions?.map((a) => (
              <div key={a._id} className="text-xs border-b border-bg-hover/40 pb-2 last:border-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="font-mono text-slate-200">{a.action}</span>
                  <StatePill value={a.status} />
                </div>
                <div className="text-slate-400 truncate" title={a.asset_id}>
                  {a.asset_name}
                </div>
                <div className="text-slate-500 mt-0.5">
                  {a.actor} ·{" "}
                  {a.timestamp ? new Date(a.timestamp).toLocaleString() : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Categories breakdown — secondary, keep but de-emphasize */}
      <div className="bg-bg-card border border-bg-hover rounded-lg p-4 mt-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Asset categories</h2>
          <Link to="/assets" className="text-xs text-slate-400 hover:text-accent">
            Browse →
          </Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-2">
          {(categories.data || []).map((c) => (
            <Link
              key={c.category}
              to={`/assets?category=${c.category}`}
              className="bg-bg-hover/40 hover:bg-bg-hover rounded p-2 text-sm flex items-center justify-between"
            >
              <span className="text-slate-300 truncate">
                {c.category.replace(/_/g, " ")}
              </span>
              <span className="text-slate-500 ml-2 shrink-0">{c.count}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
