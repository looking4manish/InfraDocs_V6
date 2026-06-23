import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import HealthBadge from "../components/HealthBadge";
import AssetRow from "../components/AssetRow";
import Breadcrumbs from "../components/Breadcrumbs";

export default function ProjectDetail() {
  const { name } = useParams();
  const q = useQuery({
    queryKey: ["project", name],
    queryFn: () => endpoints.getProject(name).then((r) => r.data),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <Breadcrumbs
            items={[
              { label: "Home", to: "/" },
              { label: "Projects", to: "/projects" },
              { label: name },
            ]}
          />
          <h1 className="text-xl font-semibold mt-1">{name}</h1>
        </div>
        {q.data && <HealthBadge score={q.data.health_score} />}
      </div>

      {q.isError && (
        <div className="text-rose-300 text-sm">
          {q.error.response?.status === 404
            ? "No assets found for this project."
            : `Failed: ${String(q.error)}`}
        </div>
      )}

      {q.data && (
        <>
          <div className="text-sm text-slate-400 mb-3">
            {q.data.asset_count} assets
          </div>
          <div className="bg-bg-card border border-bg-hover rounded-lg overflow-hidden">
            <div className="grid grid-cols-12 gap-3 px-3 py-2 text-xs uppercase tracking-wide text-slate-500 border-b border-bg-hover">
              <div className="col-span-4">Name</div>
              <div className="col-span-3">Category</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-3">Project</div>
            </div>
            {q.data.assets.map((a) => (
              <AssetRow key={a.asset_id} asset={a} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
