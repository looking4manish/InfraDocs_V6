import { Link } from "react-router-dom";
import HealthBadge from "./HealthBadge";

export default function ProjectCard({ project }) {
  return (
    <Link
      to={`/projects/${encodeURIComponent(project.name)}`}
      className="block bg-bg-card border border-bg-hover rounded-lg p-4 hover:border-accent transition"
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="font-semibold text-base">{project.name}</h3>
        <HealthBadge score={project.health_score} />
      </div>
      <div className="text-xs text-slate-400 mb-3">
        {project.asset_count} assets
      </div>
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
