import { Link } from "react-router-dom";
import { formatBytes } from "./Bytes";

function StatPair({ label, value }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="text-sm text-slate-200">{value}</span>
    </div>
  );
}

export default function AppCard({ app }) {
  const isSystem = app.type === "system";
  return (
    <Link
      to={`/applications/${encodeURIComponent(app.name)}`}
      className="block bg-bg-card border border-bg-hover rounded-lg p-4 hover:border-accent transition"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-base">{app.name}</h3>
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded ${
              isSystem
                ? "bg-slate-500/20 text-slate-300"
                : "bg-accent/15 text-accent"
            }`}
          >
            {app.type}
          </span>
        </div>
        {app.internet_exposed && (
          <span
            title={app.cloudflare ? "Internet-exposed via Cloudflare" : "Internet-exposed"}
            className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300"
          >
            {app.cloudflare ? "CF" : "live"}
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-3">
        <StatPair label="Components" value={app.components_count ?? 0} />
        <StatPair label="Ports" value={app.listening_ports?.length || 0} />
        <StatPair label="Disk" value={formatBytes(app.total_size_bytes)} />
      </div>

      {app.urls?.length > 0 && (
        <div className="text-xs text-slate-400 truncate" title={app.urls.join("\n")}>
          {app.urls[0]}
          {app.urls.length > 1 && (
            <span className="text-slate-500"> +{app.urls.length - 1}</span>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-1">
        {app.containers?.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 bg-bg-hover rounded text-slate-300">
            🐳 {app.containers.length}
          </span>
        )}
        {app.systemd_units?.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 bg-bg-hover rounded text-slate-300">
            ⚙ {app.systemd_units.length}
          </span>
        )}
        {app.nginx_sites?.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 bg-bg-hover rounded text-slate-300">
            🌐 {app.nginx_sites.length}
          </span>
        )}
        {app.volumes?.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 bg-bg-hover rounded text-slate-300">
            💾 {app.volumes.length}
          </span>
        )}
        {app.images?.length > 0 && (
          <span className="text-[10px] px-1.5 py-0.5 bg-bg-hover rounded text-slate-300">
            📦 {app.images.length}
          </span>
        )}
      </div>
    </Link>
  );
}
