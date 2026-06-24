import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Skull, ShieldAlert, Loader2, Archive, Check, X } from "lucide-react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";

// The Kill Button. Two-step: dry-run plan -> type-to-confirm -> execute.
// The backend backs up first and aborts all deletion if a backup fails.
export default function KillButton({ name }) {
  const [plan, setPlan] = useState(null);
  const [confirm, setConfirm] = useState("");
  const [result, setResult] = useState(null);

  const planMut = useMutation({
    mutationFn: () => endpoints.teardown(name, { dry_run: true }).then((r) => r.data),
    onSuccess: (d) => { setPlan(d); setResult(null); setConfirm(""); },
  });
  const killMut = useMutation({
    mutationFn: () => endpoints.teardown(name, { dry_run: false, confirm: name }).then((r) => r.data),
    onSuccess: setResult,
  });

  const refused = plan?.refusals?.length > 0;
  const armed = confirm === name && !refused;

  function fireKill() {
    if (!armed) return;
    const ok = window.confirm(
      `PERMANENTLY tear down "${name}".\n\n` +
      `A backup is written to ~/projects/backups/${name}/ first, then containers, ` +
      `nginx, volumes and the project directory are removed. Shared assets are skipped.\n\n` +
      `This cannot be undone. Continue?`
    );
    if (ok) killMut.mutate();
  }

  return (
    <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/[0.04] p-3">
      <div className="flex items-center gap-2 mb-2">
        <Skull size={14} className="text-red-400" />
        <span className="text-[13px] font-semibold text-red-300">Danger zone — Kill {name}</span>
      </div>

      {!plan && !result && (
        <button
          onClick={() => planMut.mutate()}
          disabled={planMut.isPending}
          className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-md border border-red-500/30 text-red-300 hover:bg-red-500/10 transition disabled:opacity-50"
        >
          {planMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <ShieldAlert size={12} />}
          Plan teardown (dry-run)
        </button>
      )}
      {planMut.isError && (
        <div className="text-[12px] text-amber-300/90 mt-1">
          Teardown endpoint unavailable — the API may need a restart to expose it.
        </div>
      )}

      {/* ---- dry-run plan ---- */}
      {plan && !result && (
        <div className="space-y-2.5">
          {refused ? (
            <div className="text-[12.5px] text-red-300">
              Refused: {plan.refusals.join("; ")}
            </div>
          ) : (
            <>
              <div className="text-[11px] text-zinc-500 flex items-center gap-1.5">
                <Archive size={11} /> backup → <code className="text-zinc-400">~/projects/backups/{name}/&lt;timestamp&gt;/</code>
              </div>
              <ol className="text-[12px] font-mono space-y-0.5">
                {plan.ops.map((o, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="text-zinc-600 w-4 text-right">{i + 1}</span>
                    <span className={cn(
                      "px-1.5 py-px rounded text-[10px]",
                      o.critical ? "bg-accent-cyan/15 text-accent-cyan"
                        : o.data_loss ? "bg-red-500/15 text-red-300"
                        : "bg-white/[0.06] text-zinc-400"
                    )}>{o.op}</span>
                    <span className="text-zinc-400 truncate">{o.label}</span>
                  </li>
                ))}
              </ol>
              {plan.skipped?.length > 0 && (
                <div className="text-[11px] text-amber-300/80">
                  Skipped (shared/protected): {plan.skipped.map((s) => s.name).join(", ")}
                </div>
              )}

              <div className="flex items-center gap-2 pt-1">
                <input
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder={`type "${name}" to confirm`}
                  className="bg-bg-base border border-red-500/30 rounded px-2 py-1 text-xs font-mono w-56 focus:outline-none focus:border-red-500/60"
                />
                <button
                  onClick={fireKill}
                  disabled={!armed || killMut.isPending}
                  className={cn(
                    "inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-semibold transition",
                    armed ? "bg-red-500/80 text-white hover:bg-red-500"
                          : "bg-red-500/15 text-red-300/50 cursor-not-allowed"
                  )}
                >
                  {killMut.isPending ? <Loader2 size={12} className="animate-spin" /> : <Skull size={12} />}
                  Kill {name}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ---- execution result ---- */}
      {result && (
        <div className="space-y-1.5">
          <div className={cn("text-[12.5px] font-semibold", result.aborted ? "text-amber-300" : "text-emerald-300")}>
            {result.aborted ? "Aborted after a backup failure — nothing was deleted." : `Teardown complete · backup at ${result.backup_dir}`}
          </div>
          <div className="text-[11px] font-mono space-y-0.5 max-h-52 overflow-y-auto">
            {result.results.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                {r.status === "success" ? <Check size={11} className="text-emerald-400" />
                  : r.status === "skipped" ? <span className="text-zinc-600 w-[11px] text-center">·</span>
                  : <X size={11} className="text-red-400" />}
                <span className="text-zinc-500">{r.op}</span>
                <span className="text-zinc-400 truncate">{r.target}</span>
                {r.stderr && <span className="text-red-300/70 truncate">{r.stderr}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
