import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

const MUTATING = new Set([
  "start", "stop", "restart", "up", "down", "reload",
]);

// Actions whose result is mainly stdout text — show output inline after success.
const TEXT_OUTPUT = new Set(["logs", "status", "test"]);

export default function ActionButton({
  action,
  fire,                 // () => Promise<axios response>
  disabled,
  disabledReason,
  invalidateKeys = [],  // query keys to invalidate after a successful fire
  label,
  className = "",
  size = "sm",
}) {
  const qc = useQueryClient();
  const [output, setOutput] = useState(null);
  const mut = useMutation({
    mutationFn: () => fire(),
    onSuccess: (res) => {
      const data = res?.data;
      if (data && (data.stdout || data.stderr)) {
        setOutput(data);
      } else {
        setOutput(null);
      }
      for (const k of invalidateKeys) {
        qc.invalidateQueries({ queryKey: k });
      }
    },
    onError: (err) => {
      setOutput({
        status: "error",
        stderr: err?.response?.data?.detail || String(err),
      });
    },
  });

  function onClick() {
    if (disabled) return;
    if (MUTATING.has(action)) {
      const ok = window.confirm(
        `Run "${action}"? This will affect the live host. Continue?`
      );
      if (!ok) return;
    }
    mut.mutate();
  }

  const sizeClasses =
    size === "xs"
      ? "px-2 py-0.5 text-[11px]"
      : "px-2.5 py-1 text-xs";

  const baseClasses = MUTATING.has(action)
    ? "bg-rose-500/15 text-rose-200 hover:bg-rose-500/25 border border-rose-500/20"
    : "bg-bg-hover text-slate-200 hover:bg-accent/20 hover:text-accent border border-bg-hover";

  return (
    <div className={`inline-block ${className}`}>
      <button
        onClick={onClick}
        disabled={disabled || mut.isPending}
        title={disabled ? disabledReason : ""}
        className={`rounded ${sizeClasses} ${baseClasses} disabled:opacity-40 disabled:cursor-not-allowed`}
      >
        {mut.isPending ? "…" : (label || action)}
      </button>
      {output && (
        <ActionOutputModal
          action={action}
          output={output}
          onClose={() => setOutput(null)}
          asText={TEXT_OUTPUT.has(action)}
        />
      )}
    </div>
  );
}

function ActionOutputModal({ action, output, onClose, asText }) {
  const isError = output.status === "error" || output.status === "failed";
  return (
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-bg-panel border border-bg-hover rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-bg-hover">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{action}</span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded ${
                isError
                  ? "bg-rose-500/20 text-rose-300"
                  : "bg-emerald-500/20 text-emerald-300"
              }`}
            >
              {output.status || "ok"}
            </span>
            {output.duration_ms != null && (
              <span className="text-xs text-slate-500">
                {output.duration_ms} ms
              </span>
            )}
            {output.return_code != null && (
              <span className="text-xs text-slate-500">
                rc={output.return_code}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-lg leading-none"
          >
            ×
          </button>
        </div>
        <div className="overflow-y-auto p-4 space-y-3">
          {output.stdout && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
                stdout
              </div>
              <pre className={`text-xs bg-bg-base border border-bg-hover rounded p-3 ${asText ? "whitespace-pre-wrap" : "overflow-x-auto"}`}>
                {output.stdout}
              </pre>
            </div>
          )}
          {output.stderr && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">
                stderr
              </div>
              <pre className={`text-xs bg-bg-base border border-rose-500/20 rounded p-3 text-rose-300 ${asText ? "whitespace-pre-wrap" : "overflow-x-auto"}`}>
                {output.stderr}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
