import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import HealthBadge from "../components/HealthBadge";

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-bg-card border border-bg-hover rounded-lg p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => endpoints.listProjects().then((r) => r.data),
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => endpoints.assetCategories().then((r) => r.data.categories),
  });
  const scans = useQuery({
    queryKey: ["scans"],
    queryFn: () => endpoints.listScans(5).then((r) => r.data),
    refetchInterval: 3000,
  });

  const totalAssets =
    (categories.data || []).reduce((sum, c) => sum + c.count, 0) || 0;
  const projectCount = projects.data?.count ?? 0;
  const lastScan = scans.data?.scans?.[0];

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard label="Projects" value={projectCount} />
        <StatCard label="Total Assets" value={totalAssets} />
        <StatCard
          label="Last Scan"
          value={
            lastScan ? `${lastScan.total_assets ?? "-"} assets` : "—"
          }
          sub={
            lastScan?.started_at
              ? new Date(lastScan.started_at).toLocaleString()
              : null
          }
        />
        <StatCard
          label="Last Scan Status"
          value={lastScan?.status ?? "—"}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-bg-card border border-bg-hover rounded-lg p-4">
          <h2 className="font-semibold mb-3">Projects</h2>
          {projects.isLoading && <div className="text-sm text-slate-400">Loading…</div>}
          {projects.data?.projects?.map((p) => (
            <div
              key={p.name}
              className="flex items-center justify-between py-2 border-b border-bg-hover/40 last:border-0 text-sm"
            >
              <div>{p.name}</div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-400">{p.asset_count}</span>
                <HealthBadge score={p.health_score} />
              </div>
            </div>
          ))}
        </div>

        <div className="bg-bg-card border border-bg-hover rounded-lg p-4">
          <h2 className="font-semibold mb-3">Categories</h2>
          {(categories.data || []).map((c) => (
            <div
              key={c.category}
              className="flex items-center justify-between py-1.5 text-sm"
            >
              <div className="text-slate-300">
                {c.category.replace(/_/g, " ")}
              </div>
              <div className="text-slate-400">{c.count}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
