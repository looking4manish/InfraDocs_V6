import { Link } from "react-router-dom";
import HealthBadge from "./HealthBadge";

export default function ProjectCard({ project }) {
  return (
    <Link
      to={`/projects/${encodeURIComponent(project.name)}`}
      className="block neon-panel neon-panel-hover rounded-lg p-4 transition"
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="font-semibold text-base">{project.name}</h3>
        <HealthBadge score={project.health_score} />
      </div>
      <div className="text-xs text-slate-400 mb-1">
        {project.asset_count} assets
      </div>
      {project.root_path && (
        <div
          className="text-[10px] font-mono text-zinc-500 mb-3 truncate"
          title={project.root_path}
        >
          {project.root_path}
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        {Object.entries(project.categories || {}).map(([cat, count]) => (
          <span
            key={cat}
            className="text-[10px] px-2 py-0.5 bg-bg-hover rounded text-slate-300"
          >
            {cat.replace("_", " ")} · {count}
          </span>
        ))}
      </div>
    </Link>
  );
}
