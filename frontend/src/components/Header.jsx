import { useMutation, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api/client";

export default function Header({ onSearch }) {
  const qc = useQueryClient();
  const triggerScan = useMutation({
    mutationFn: () => endpoints.triggerScan(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scans"] });
    },
  });

  return (
    <header className="h-14 flex items-center px-4 border-b border-bg-card bg-bg-panel">
      <div className="font-semibold text-lg mr-6">
        <span className="text-accent">Infra</span>Docs
        <span className="ml-1 text-xs text-slate-400">v6</span>
      </div>
      <input
        type="search"
        placeholder="Search assets / projects…"
        onChange={(e) => onSearch?.(e.target.value)}
        className="flex-1 max-w-md bg-bg-card border border-bg-hover rounded px-3 py-1.5 text-sm focus:outline-none focus:border-accent"
      />
      <div className="ml-auto flex items-center gap-3">
        <button
          onClick={() => triggerScan.mutate()}
          disabled={triggerScan.isPending}
          className="bg-accent hover:bg-accent-dim disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded"
        >
          {triggerScan.isPending ? "Scanning…" : "🔄 Scan now"}
        </button>
        <div className="text-xs text-slate-400">
          {triggerScan.isSuccess && `queued: ${triggerScan.data.data.scan_id.slice(0, 8)}`}
        </div>
      </div>
    </header>
  );
}
