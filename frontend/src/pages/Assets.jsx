import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import AssetRow from "../components/AssetRow";

export default function Assets() {
  const [params, setParams] = useSearchParams();
  const filters = {
    category: params.get("category") || undefined,
    project: params.get("project") || undefined,
    status: params.get("status") || undefined,
  };

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

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Assets</h1>
      <div className="flex flex-wrap gap-2 mb-3 text-sm">
        {["category", "project", "status"].map((k) => (
          <input
            key={k}
            value={params.get(k) || ""}
            onChange={(e) => update(k, e.target.value)}
            placeholder={`Filter by ${k}`}
            className="bg-bg-card border border-bg-hover rounded px-2 py-1 text-xs"
          />
        ))}
        {(filters.category || filters.project || filters.status) && (
          <button
            onClick={() => setParams({})}
            className="text-xs text-slate-400 hover:text-accent"
          >
            Clear
          </button>
        )}
      </div>
      <div className="text-xs text-slate-500 mb-2">
        {q.data ? `${q.data.count} results` : ""}
      </div>
      <div className="bg-bg-card border border-bg-hover rounded-lg overflow-hidden">
        <div className="grid grid-cols-12 gap-3 px-3 py-2 text-xs uppercase tracking-wide text-slate-500 border-b border-bg-hover">
          <div className="col-span-4">Name</div>
          <div className="col-span-3">Category</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-3">Project</div>
        </div>
        {q.isLoading && (
          <div className="p-4 text-sm text-slate-400">Loading…</div>
        )}
        {q.data?.assets?.map((a) => (
          <AssetRow key={a.asset_id} asset={a} />
        ))}
      </div>
    </div>
  );
}
