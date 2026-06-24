import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import StatePill from "../components/StatePill";

export default function Actions() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [assetId, setAssetId] = useState("");
  const [limit, setLimit] = useState(50);
  const [open, setOpen] = useState(null);

  const allowed = useQuery({
    queryKey: ["actions-allowed"],
    queryFn: () => endpoints.allowedActions().then((r) => r.data),
  });
  const list = useQuery({
    queryKey: ["actions-list", { actor, action, assetId, limit }],
    queryFn: () =>
      endpoints
        .listActions({
          actor: actor || undefined,
          action: action || undefined,
          asset_id: assetId || undefined,
          limit,
        })
        .then((r) => r.data),
    refetchInterval: 5000,
  });

  const allActions = Object.values(allowed.data?.allowed || {}).flat();
  const uniqueActions = Array.from(new Set(allActions)).sort();

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Actions log</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Every operational action attempt — success, failed, refused — is
          recorded here with actor, asset, status, return code, and trimmed
          stdout/stderr. Polls every 5s.
        </p>
      </div>

      <div className="neon-panel rounded-lg p-3 mb-3">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
              action
            </label>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs"
            >
              <option value="">all</option>
              {uniqueActions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
              actor
            </label>
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="username"
              className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs w-32"
            />
          </div>
          <div className="flex-1 min-w-[200px]">
            <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
              asset_id
            </label>
            <input
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              placeholder="oci:container:..."
              className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs w-full font-mono"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
              limit
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs"
            >
              {[25, 50, 100, 250].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="ml-auto text-xs text-slate-500">
            {list.data ? `${list.data.count} entries` : "—"}
          </div>
        </div>
      </div>

      <div className="neon-panel rounded-lg overflow-hidden">
        <div className="grid grid-cols-12 gap-2 px-3 py-2 text-xs uppercase tracking-wide text-slate-500 border-b border-bg-hover">
          <div className="col-span-2">When</div>
          <div className="col-span-1">Actor</div>
          <div className="col-span-1">Action</div>
          <div className="col-span-3">Asset</div>
          <div className="col-span-2">Category</div>
          <div className="col-span-1">Status</div>
          <div className="col-span-1 text-right">ms</div>
          <div className="col-span-1">Refused</div>
        </div>
        {list.isLoading && (
          <div className="p-4 text-sm text-slate-400">Loading…</div>
        )}
        {list.data?.actions?.map((a) => (
          <div key={a._id}>
            <button
              onClick={() => setOpen(open === a._id ? null : a._id)}
              className="w-full grid grid-cols-12 gap-2 px-3 py-2 border-b border-bg-card text-sm hover:bg-bg-hover/40 text-left items-center"
            >
              <div className="col-span-2 text-xs text-slate-400">
                {new Date(a.timestamp).toLocaleString()}
              </div>
              <div className="col-span-1 text-xs text-slate-300">{a.actor}</div>
              <div className="col-span-1 font-mono text-xs">{a.action}</div>
              <div className="col-span-3 truncate text-xs text-slate-200" title={a.asset_id}>
                {a.asset_name || a.asset_id}
              </div>
              <div className="col-span-2 text-xs text-slate-400 truncate">
                {a.category}
              </div>
              <div className="col-span-1">
                <StatePill value={a.status} />
              </div>
              <div className="col-span-1 text-right text-xs text-slate-500">
                {a.duration_ms ?? "—"}
              </div>
              <div className="col-span-1 text-xs text-rose-300/80">
                {a.refused_reason || ""}
              </div>
            </button>
            {open === a._id && (
              <div className="px-4 py-3 bg-bg-base/50 border-b border-bg-card space-y-2">
                {a.stdout && (
                  <details open>
                    <summary className="text-[10px] uppercase tracking-wide text-slate-500 cursor-pointer">
                      stdout ({a.stdout.length}b)
                    </summary>
                    <pre className="text-xs mt-1 whitespace-pre-wrap bg-bg-base border border-bg-hover rounded p-2 max-h-60 overflow-y-auto">
                      {a.stdout}
                    </pre>
                  </details>
                )}
                {a.stderr && (
                  <details open>
                    <summary className="text-[10px] uppercase tracking-wide text-slate-500 cursor-pointer">
                      stderr
                    </summary>
                    <pre className="text-xs mt-1 whitespace-pre-wrap bg-bg-base border border-rose-500/20 rounded p-2 text-rose-300 max-h-60 overflow-y-auto">
                      {a.stderr}
                    </pre>
                  </details>
                )}
                <div className="text-[11px] text-slate-500 font-mono">
                  {a.asset_id} · args: {JSON.stringify(a.args || {})}
                </div>
              </div>
            )}
          </div>
        ))}
        {list.data && list.data.count === 0 && (
          <div className="p-4 text-sm text-slate-400">No actions yet.</div>
        )}
      </div>
    </div>
  );
}
