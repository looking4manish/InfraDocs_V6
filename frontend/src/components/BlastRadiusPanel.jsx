import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ChevronDown, Database, Link2, ShieldCheck,
  Box, Package, Globe, Cog, Layers, Folder, FileLock2,
} from "lucide-react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";

const CAT_ICON = {
  docker_container: Box,
  docker_image: Package,
  docker_volume: Database,
  nginx_server_block: Globe,
  tls_certificate: FileLock2,
  systemd_unit: Cog,
  docker_compose: Layers,
  project_directory: Folder,
};

function Badge({ tone, children }) {
  const tones = {
    red: "bg-red-500/15 text-red-300",
    amber: "bg-amber-500/15 text-amber-300",
    cyan: "bg-accent-cyan/15 text-accent-cyan",
  };
  return (
    <span className={cn("text-[10px] font-semibold px-1.5 py-px rounded", tones[tone])}>
      {children}
    </span>
  );
}

// Read-only teardown preview: what a "kill" would touch, with data-loss + shared
// flags. No destructive action — that gate isn't built yet.
export default function BlastRadiusPanel({ name }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["blast-radius", name],
    queryFn: () => endpoints.blastRadius(name).then((r) => r.data),
    enabled: open,
  });

  const data = q.data;
  return (
    <section className="neon-panel rounded-lg mb-4">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left"
      >
        <AlertTriangle size={14} className="text-amber-400 shrink-0" />
        <span className="font-semibold text-sm">Blast radius</span>
        <span className="text-[11px] text-zinc-500">teardown preview · read-only</span>
        {data && (
          <span className="text-[11px] text-zinc-500 font-mono">
            · {data.summary.total} assets
            {data.summary.data_loss > 0 && ` · ${data.summary.data_loss} data-loss`}
            {data.summary.shared > 0 && ` · ${data.summary.shared} shared`}
          </span>
        )}
        <ChevronDown
          size={15}
          className={cn("ml-auto text-zinc-500 transition", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="px-4 pb-4">
          {q.isLoading && (
            <div className="text-sm text-zinc-500 animate-pulse">Computing impact…</div>
          )}
          {q.isError && (
            <div className="text-sm text-amber-300/90">
              Blast-radius endpoint unavailable — the API may need a restart to expose it
              (<code className="text-zinc-400">sudo systemctl restart infradocs-v6-api.service</code>).
            </div>
          )}

          {data && (
            <>
              {data.warnings.length > 0 && (
                <div className="space-y-1.5 mb-3">
                  {data.warnings.map((w, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 text-[12.5px] text-amber-300/90 bg-amber-500/[0.06] border border-amber-500/20 rounded-lg px-3 py-2"
                    >
                      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                      <span>{w}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="space-y-1">
                {data.items.map((it, i) => {
                  const Icon = CAT_ICON[it.category] || Box;
                  const isProtected = (data.protected || []).includes(it.name);
                  return (
                    <div
                      key={i}
                      className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-bg-card border border-bg-hover/60 text-[13px]"
                    >
                      <Icon size={14} className="text-zinc-500 shrink-0" />
                      <span className="text-[10px] uppercase tracking-wide text-zinc-600 w-28 shrink-0">
                        {it.category.replace(/_/g, " ")}
                      </span>
                      <span className="font-mono text-zinc-200 truncate">{it.name}</span>
                      <span className="ml-auto flex items-center gap-1.5 shrink-0">
                        {it.data_loss && <Badge tone="red"><Database size={9} className="inline mr-0.5" />data loss</Badge>}
                        {it.shared && (
                          <Badge tone="amber">
                            <Link2 size={9} className="inline mr-0.5" />
                            shared · {it.shared_with.join(", ")}
                          </Badge>
                        )}
                        {isProtected && <Badge tone="cyan"><ShieldCheck size={9} className="inline mr-0.5" />protected</Badge>}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="text-[11px] text-zinc-600 mt-3">
                Preview only — no teardown action exists yet. Red = removal destroys
                data · amber = shared with another app (must not be removed).
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
