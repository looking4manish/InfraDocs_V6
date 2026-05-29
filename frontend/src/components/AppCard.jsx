import { Link } from "react-router-dom";
import { Container, Cog, Globe, HardDrive, Package, CircleDashed } from "lucide-react";
import { cn } from "../lib/cn";
import { formatBytes } from "./Bytes";

function Chip({ icon: Icon, n, label }) {
  return (
    <span
      title={label}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-bg-hover"
    >
      <Icon size={13} className="opacity-80" />
      {n}
    </span>
  );
}

export default function AppCard({ app, active = false }) {
  const isSystem = app.type === "system";
  const hasRuntime =
    (app.components_count ?? 0) > 0 ||
    (app.containers?.length || 0) > 0 ||
    (app.systemd_units?.length || 0) > 0 ||
    (app.listening_ports?.length || 0) > 0;

  const dotColor = !hasRuntime
    ? "bg-slate-500"
    : app.internet_exposed
    ? "bg-emerald-400"
    : "bg-sky-400";

  return (
    <Link
      to={`/applications/${encodeURIComponent(app.name)}`}
      className={cn(
        "group block bg-bg-card border rounded-lg p-4 transition",
        active
          ? "border-accent ring-1 ring-accent/40"
          : "border-bg-hover hover:border-slate-600",
        !hasRuntime && "opacity-80"
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("w-2 h-2 rounded-full shrink-0", dotColor)} />
        <h3
          className={cn(
            "font-medium text-[15px] truncate",
            !hasRuntime && "text-slate-400"
          )}
        >
          {app.name}
        </h3>
        <span
          className={cn(
            "text-[10px] px-1.5 py-0.5 rounded-full shrink-0",
            isSystem
              ? "bg-slate-500/20 text-slate-300"
              : "bg-accent/15 text-accent"
          )}
        >
          {app.type}
        </span>
        {app.internet_exposed && (
          <span
            title={
              app.cloudflare ? "Internet-exposed via Cloudflare" : "Internet-exposed"
            }
            className="ml-auto shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300"
          >
            {app.cloudflare ? "CF" : "live"}
          </span>
        )}
      </div>

      {hasRuntime ? (
        <>
          <div className="mt-2.5 text-[13px] text-slate-400 font-mono tabular-nums tracking-tight">
            {app.components_count ?? 0} components · {app.listening_ports?.length || 0}{" "}
            ports · {formatBytes(app.total_size_bytes)}
          </div>
          {app.urls?.length > 0 && (
            <div
              className="mt-1.5 text-xs text-slate-500 truncate"
              title={app.urls.join("\n")}
            >
              {app.urls[0]}
              {app.urls.length > 1 && (
                <span className="text-slate-600"> +{app.urls.length - 1}</span>
              )}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5 text-[12px] text-slate-400">
            {app.containers?.length > 0 && (
              <Chip icon={Container} n={app.containers.length} label="containers" />
            )}
            {app.systemd_units?.length > 0 && (
              <Chip icon={Cog} n={app.systemd_units.length} label="services" />
            )}
            {app.nginx_sites?.length > 0 && (
              <Chip icon={Globe} n={app.nginx_sites.length} label="nginx sites" />
            )}
            {app.volumes?.length > 0 && (
              <Chip icon={HardDrive} n={app.volumes.length} label="volumes" />
            )}
            {app.images?.length > 0 && (
              <Chip icon={Package} n={app.images.length} label="images" />
            )}
          </div>
        </>
      ) : (
        <div className="mt-3 flex items-center gap-2 text-[13px] text-slate-500">
          <CircleDashed size={15} />
          {app.total_size_bytes
            ? `No live runtime · ${formatBytes(app.total_size_bytes)} on disk`
            : "No live runtime — folder tracked only"}
        </div>
      )}
    </Link>
  );
}
