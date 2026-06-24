import { useQuery } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { endpoints } from "../api/client";
import { formatBytes } from "../components/Bytes";
import UsageBar from "../components/UsageBar";

function StatCard({ label, value, sub }) {
  return (
    <div className="neon-panel rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="text-xl font-semibold mt-0.5">{value}</div>
      {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

const KIND_LABELS = {
  mount: "Mounts",
  docker_volume: "Docker volumes",
  project_tree: "Project trees",
  bind_mount: "Bind mounts",
};

export default function Storage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") || "";
  const project = params.get("project") || "";

  const summary = useQuery({
    queryKey: ["storage-summary"],
    queryFn: () => endpoints.storageSummary().then((r) => r.data),
  });
  const list = useQuery({
    queryKey: ["storage-list", { kind, project }],
    queryFn: () =>
      endpoints
        .listStorage({
          kind: kind || undefined,
          project: project || undefined,
        })
        .then((r) => r.data),
  });

  const byKind = summary.data?.by_kind || [];
  const byOwner = summary.data?.by_owner || [];

  function setKind(k) {
    const next = new URLSearchParams(params);
    if (k) next.set("kind", k);
    else next.delete("kind");
    setParams(next);
  }
  function setProject(p) {
    const next = new URLSearchParams(params);
    if (p) next.set("project", p);
    else next.delete("project");
    setParams(next);
  }

  const totalBytes = byKind.reduce((s, k) => s + (k.size_bytes || 0), 0);

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Storage</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Unified registry: filesystem mounts + docker volumes + project trees +
          container bind mounts. Every byte is owned by a project or System.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <StatCard label="Total entities" value={summary.data?.total ?? "—"} />
        <StatCard label="Total tracked" value={formatBytes(totalBytes)} />
        {byKind.slice(0, 3).map((k) => (
          <StatCard
            key={k.kind}
            label={KIND_LABELS[k.kind] || k.kind}
            value={k.count}
            sub={formatBytes(k.size_bytes)}
          />
        ))}
      </div>

      {/* Owner breakdown — quick visual */}
      <div className="neon-panel rounded-lg p-4 mb-4">
        <h2 className="text-sm font-semibold mb-3">Storage by owner</h2>
        {byOwner.map((o) => {
          const pct = totalBytes
            ? Math.round((o.size_bytes / totalBytes) * 100)
            : 0;
          return (
            <div key={o.project} className="mb-2 last:mb-0">
              <div className="flex items-center justify-between text-xs mb-1">
                <Link
                  to={`/applications/${encodeURIComponent(o.project)}`}
                  className="text-accent hover:underline"
                >
                  {o.project}
                </Link>
                <span className="text-slate-400">
                  {formatBytes(o.size_bytes)}{" "}
                  <span className="text-slate-500">({pct}%)</span>
                </span>
              </div>
              <div className="h-1.5 bg-bg-hover rounded overflow-hidden">
                <div
                  className="h-full bg-accent"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Kind filter tabs */}
      <div className="flex flex-wrap gap-2 mb-3 text-sm">
        <button
          onClick={() => setKind("")}
          className={`px-3 py-1 rounded border text-xs ${
            !kind
              ? "border-accent text-accent bg-accent/10"
              : "border-bg-hover text-slate-400 hover:text-slate-200"
          }`}
        >
          All <span className="text-slate-500">· {summary.data?.total ?? 0}</span>
        </button>
        {byKind.map((k) => (
          <button
            key={k.kind}
            onClick={() => setKind(k.kind)}
            className={`px-3 py-1 rounded border text-xs ${
              kind === k.kind
                ? "border-accent text-accent bg-accent/10"
                : "border-bg-hover text-slate-400 hover:text-slate-200"
            }`}
          >
            {KIND_LABELS[k.kind] || k.kind}{" "}
            <span className="text-slate-500">· {k.count}</span>
          </button>
        ))}
      </div>

      {project && (
        <div className="text-xs text-slate-400 mb-2">
          Filtered to project:{" "}
          <span className="text-accent font-semibold">{project}</span>{" "}
          <button
            onClick={() => setProject("")}
            className="ml-2 text-slate-500 hover:text-accent"
          >
            (clear)
          </button>
        </div>
      )}

      <div className="neon-panel rounded-lg overflow-hidden">
        <div className="grid grid-cols-12 gap-2 px-3 py-2 text-xs uppercase tracking-wide text-slate-500 border-b border-bg-hover">
          <div className="col-span-2">Kind</div>
          <div className="col-span-4">Name / Path</div>
          <div className="col-span-2">Owner</div>
          <div className="col-span-2 text-right">Size</div>
          <div className="col-span-2">Usage / fstype</div>
        </div>
        {list.isLoading && (
          <div className="p-4 text-sm text-slate-400">Loading…</div>
        )}
        {list.data?.storage?.map((s) => (
          <div
            key={s.storage_id}
            className="grid grid-cols-12 gap-2 px-3 py-2 border-b border-bg-card text-sm hover:bg-bg-hover/40 items-center"
          >
            <div className="col-span-2">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-hover text-slate-400">
                {s.kind}
              </span>
            </div>
            <div className="col-span-4 truncate" title={s.path || s.name}>
              <span className="text-slate-200">{s.name}</span>
              {s.path && s.path !== s.name && (
                <span className="text-xs text-slate-500 font-mono ml-2">
                  {s.path}
                </span>
              )}
            </div>
            <div className="col-span-2">
              <button
                onClick={() => setProject(s.owner_project)}
                className="text-xs text-accent hover:underline"
              >
                {s.owner_project}
              </button>
            </div>
            <div className="col-span-2 text-right text-slate-300 text-xs">
              {formatBytes(s.size_bytes)}
              {s.total_bytes && (
                <div className="text-[10px] text-slate-500">
                  of {formatBytes(s.total_bytes)}
                </div>
              )}
            </div>
            <div className="col-span-2 text-xs text-slate-400">
              {s.kind === "mount" && s.usage_percent != null ? (
                <UsageBar percent={s.usage_percent} />
              ) : s.fstype ? (
                s.fstype
              ) : (
                "—"
              )}
            </div>
          </div>
        ))}
        {list.data && list.data.count === 0 && (
          <div className="p-4 text-sm text-slate-400">No storage entities match.</div>
        )}
      </div>
    </div>
  );
}
