import { Link } from "react-router-dom";
import { Container, Cog, Globe, HardDrive, Package } from "lucide-react";
import { cn } from "../lib/cn";
import { formatBytes } from "./Bytes";

function Mini({ icon: Icon, n, label }) {
  return (
    <span
      title={label}
      className="inline-flex items-center gap-1 text-zinc-500 tabular-nums"
    >
      <Icon size={13} /> {n}
    </span>
  );
}

export default function AppRow({ app, active = false }) {
  const hasRuntime =
    (app.components_count ?? 0) > 0 ||
    (app.containers?.length || 0) > 0 ||
    (app.systemd_units?.length || 0) > 0 ||
    (app.listening_ports?.length || 0) > 0;
  const dot = hasRuntime ? "bg-emerald-400" : "bg-zinc-600";

  return (
    <Link
      to={`/applications/${encodeURIComponent(app.name)}`}
      className={cn(
        "group flex items-center gap-3 pl-3 pr-4 h-[52px] border-l-2 transition",
        active
          ? "border-accent bg-accent/[0.08]"
          : "border-transparent hover:bg-white/[0.03]"
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)} />
      <span
        className={cn(
          "text-[14px] font-medium truncate max-w-[200px]",
          !hasRuntime && "text-zinc-500"
        )}
      >
        {app.name}
      </span>
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-zinc-400 shrink-0">
        {app.type}
      </span>
      {app.internet_exposed && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 shrink-0">
          {app.cloudflare ? "CF" : "live"}
        </span>
      )}
      {app.urls?.length > 0 && (
        <span className="hidden lg:inline text-[12px] text-zinc-600 font-mono truncate max-w-[220px]">
          {app.urls[0].replace(/^https?:\/\//, "")}
        </span>
      )}

      <span className="flex-1" />

      {hasRuntime ? (
        <>
          <span className="hidden md:flex items-center gap-3.5 text-[12px]">
            {app.containers?.length > 0 && (
              <Mini icon={Container} n={app.containers.length} label="containers" />
            )}
            {app.systemd_units?.length > 0 && (
              <Mini icon={Cog} n={app.systemd_units.length} label="services" />
            )}
            {app.nginx_sites?.length > 0 && (
              <Mini icon={Globe} n={app.nginx_sites.length} label="nginx sites" />
            )}
            {app.volumes?.length > 0 && (
              <Mini icon={HardDrive} n={app.volumes.length} label="volumes" />
            )}
            {app.images?.length > 0 && (
              <Mini icon={Package} n={app.images.length} label="images" />
            )}
          </span>
          <span className="w-14 text-right text-[12px] text-zinc-500 font-mono tabular-nums shrink-0">
            {app.listening_ports?.length || 0} p
          </span>
          <span className="w-20 text-right text-[12px] text-zinc-300 font-mono tabular-nums shrink-0">
            {formatBytes(app.total_size_bytes)}
          </span>
        </>
      ) : (
        <span className="text-[12px] text-zinc-600 shrink-0">
          idle{app.total_size_bytes ? ` · ${formatBytes(app.total_size_bytes)}` : ""}
        </span>
      )}
    </Link>
  );
}
