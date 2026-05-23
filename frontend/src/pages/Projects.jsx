import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import ProjectCard from "../components/ProjectCard";

export default function Projects() {
  const q = useQuery({
    queryKey: ["projects"],
    queryFn: () => endpoints.listProjects().then((r) => r.data),
  });

  return (
    <div>
      <h1 className="text-xl font-semibold mb-4">Projects</h1>
      {q.isLoading && <div className="text-slate-400">Loading…</div>}
      {q.isError && (
        <div className="text-rose-300">Failed: {String(q.error)}</div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {q.data?.projects?.map((p) => (
          <ProjectCard key={p.name} project={p} />
        ))}
      </div>
    </div>
  );
}
