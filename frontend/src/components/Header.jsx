import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";

export default function Header() {
  const qc = useQueryClient();
  const triggerScan = useMutation({
    mutationFn: () => endpoints.triggerScan(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scans"] });
    },
  });

  return (
    <header className="h-14 shrink-0 flex items-center gap-4 px-4 border-b border-bg-hover bg-bg-panel">
      <div className="flex items-baseline gap-1.5 select-none">
        <span className="text-[15px] font-semibold tracking-tight text-zinc-100">
          InfraDocs
        </span>
        <span className="text-[11px] text-zinc-500 font-mono">v6</span>
      </div>

      <div className="relative flex-1 max-w-md">
        <input
          type="search"
          placeholder="Search assets, projects, ports…"
          className="w-full bg-bg-card border border-bg-hover rounded-md pl-3 pr-12 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:border-zinc-500 transition"
        />
        <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-zinc-500 border border-bg-hover rounded px-1.5 py-0.5 font-mono">
          ⌘K
        </kbd>
      </div>

      <button
        onClick={() => triggerScan.mutate()}
        disabled={triggerScan.isPending}
        className="ml-auto inline-flex items-center gap-1.5 bg-accent hover:bg-accent-dim text-black text-sm font-medium px-3 py-1.5 rounded-md disabled:opacity-50 transition"
      >
        <RefreshCw size={14} className={cn(triggerScan.isPending && "animate-spin")} />
        {triggerScan.isPending ? "Scanning…" : "Scan now"}
      </button>

      {triggerScan.isSuccess && (
        <span className="text-xs text-zinc-500 font-mono">
          queued {triggerScan.data.data.scan_id.slice(0, 8)}
        </span>
      )}
    </header>
  );
}
