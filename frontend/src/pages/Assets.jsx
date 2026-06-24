import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import AssetRow from "../components/AssetRow";
import PageHeader from "../components/PageHeader";

export default function Assets() {
  const [params, setParams] = useSearchParams();
  const filters = {
    category: params.get("category") || undefined,
    project: params.get("project") || undefined,
    status: params.get("status") || undefined,
  };
  const filtered = Boolean(filters.category || filters.project || filters.status);

  const q = useQuery({
    queryKey: ["assets", filters],
    queryFn: () => endpoints.listAssets(filters).then((r) => r.data),
  });

  function update(key, value) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  const assets = useMemo(() => q.data?.assets || [], [q.data]);
  const stats = useMemo(() => {
    const cats = new Set(assets.map((a) => a.category));
    const projs = new Set(assets.map((a) => a.project).filter(Boolean));
    const running = assets.filter((a) =>
      ["running", "active", "listening", "mounted", "in_use", "configured"].includes(a.status)
    ).length;
    return [
      { label: filtered ? "Matches" : "Total assets", value: q.data?.count ?? "—" },
      { label: "Categories", value: cats.size || "—" },
      { label: "Projects", value: projs.size || "—" },
      { label: "Active", value: running || "—", tone: "#00ED64" },
    ];
  }, [assets, q.data, filtered]);

  return (
    <div>
      <PageHeader
        title="Assets"
        subtitle="Every scanned entity — filter by category, project, or status. Click a row to inspect + act."
        stats={stats}
      />

      <div className="flex flex-wrap gap-2 mb-3 text-sm">
        {["category", "project", "status"].map((k) => (
          <input
            key={k}
            value={params.get(k) || ""}
            onChange={(e) => update(k, e.target.value)}
            placeholder={`Filter by ${k}`}
            className="bg-bg-card border border-bg-hover rounded-md px-2.5 py-1 text-xs focus:outline-none focus:border-accent/50 transition"
          />
        ))}
        {filtered && (
          <button
            onClick={() => setParams({})}
            className="text-xs text-slate-400 hover:text-accent transition"
          >
            Clear
          </button>
        )}
      </div>

      <div className="neon-panel rounded-xl overflow-hidden">
        <div className="grid grid-cols-12 gap-3 px-3 py-2 text-[10px] uppercase tracking-[0.08em] text-slate-500 border-b border-bg-hover/60">
          <div className="col-span-4">Name</div>
          <div className="col-span-3">Category</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-3">Project</div>
        </div>
        {q.isLoading && <div className="p-4 text-sm text-slate-400">Loading…</div>}
        {!q.isLoading && assets.length === 0 && (
          <div className="p-6 text-sm text-slate-500">No assets match.</div>
        )}
        {assets.map((a) => (
          <AssetRow key={a.asset_id} asset={a} />
        ))}
      </div>
    </div>
  );
}
