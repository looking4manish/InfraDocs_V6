import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { endpoints } from "../api/client";
import StatePill from "../components/StatePill";

function EvidenceBadges({ sources }) {
  return (
    <div className="flex flex-wrap gap-1">
      {(sources || []).map((s, i) => (
        <span
          key={i}
          title={s.source}
          className="text-[10px] px-1.5 py-0.5 bg-bg-hover rounded text-slate-400"
        >
          {s.kind}
        </span>
      ))}
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="bg-bg-card border border-bg-hover rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="text-xl font-semibold mt-0.5">{value}</div>
    </div>
  );
}

function ProbeWidget() {
  const [range, setRange] = useState("8000-8050");
  const [proto, setProto] = useState("tcp");
  const probe = useMutation({
    mutationFn: () => endpoints.probePorts(range, proto).then((r) => r.data),
  });

  return (
    <section className="bg-bg-card border border-bg-hover rounded-lg p-4 mb-4">
      <div className="flex items-end gap-3 flex-wrap mb-3">
        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
            Range or single port
          </label>
          <input
            value={range}
            onChange={(e) => setRange(e.target.value)}
            className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-sm font-mono w-40"
            placeholder="8000-9000"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
            Protocol
          </label>
          <select
            value={proto}
            onChange={(e) => setProto(e.target.value)}
            className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-sm"
          >
            <option value="tcp">tcp</option>
            <option value="udp">udp</option>
          </select>
        </div>
        <button
          onClick={() => probe.mutate()}
          disabled={probe.isPending}
          className="bg-accent hover:bg-accent-dim disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded"
        >
          {probe.isPending ? "Probing…" : "Probe live"}
        </button>
        <p className="text-xs text-slate-500 ml-auto max-w-md">
          On-demand <code>ss</code> snapshot. Not persisted. Cap 5000 ports.
        </p>
      </div>

      {probe.isError && (
        <div className="text-rose-300 text-sm">
          {probe.error.response?.data?.detail || String(probe.error)}
        </div>
      )}

      {probe.data && (
        <div className="mt-2">
          <div className="text-xs text-slate-400 mb-2">
            {probe.data.in_use_count} of {probe.data.count} in use across{" "}
            {probe.data.range[0]}–{probe.data.range[1]}
          </div>
          <div className="flex flex-wrap gap-1 max-h-48 overflow-y-auto">
            {probe.data.ports.map((p) => (
              <span
                key={p.port}
                className={`text-[11px] font-mono px-1.5 py-0.5 rounded ${
                  p.state === "in_use"
                    ? "bg-emerald-500/20 text-emerald-300"
                    : "bg-bg-hover text-slate-500"
                }`}
                title={p.local_address || ""}
              >
                {p.port}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default function Ports() {
  const [params, setParams] = useSearchParams();
  const filters = {
    state: params.get("state") || undefined,
    project: params.get("project") || undefined,
    port_min: params.get("port_min") || undefined,
    port_max: params.get("port_max") || undefined,
  };
  const summary = useQuery({
    queryKey: ["ports-summary"],
    queryFn: () => endpoints.portsSummary().then((r) => r.data),
  });
  const list = useQuery({
    queryKey: ["ports-list", filters],
    queryFn: () => endpoints.listPorts(filters).then((r) => r.data),
  });

  function update(k, v) {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next);
  }

  const owners = summary.data?.by_owner || [];

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold">Ports</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Hybrid registry: one row per (port, proto), deduped across listening +
          compose + nginx + systemd evidence. <code>Probe</code> hits{" "}
          <code>ss</code> live for an arbitrary range.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <StatCard label="Total" value={summary.data?.total ?? "—"} />
        <StatCard
          label="In use"
          value={summary.data?.by_state?.in_use ?? "—"}
        />
        <StatCard
          label="Declared only"
          value={summary.data?.by_state?.declared ?? "—"}
        />
        {owners.slice(0, 2).map((o) => (
          <StatCard
            key={o.project}
            label={o.project}
            value={o.count}
          />
        ))}
      </div>

      <ProbeWidget />

      <div className="bg-bg-card border border-bg-hover rounded-lg p-3 mb-3">
        <div className="flex flex-wrap gap-2 items-end">
          <FilterPill
            label="state"
            value={filters.state}
            options={["in_use", "declared"]}
            onChange={(v) => update("state", v)}
          />
          <FilterPill
            label="project"
            value={filters.project}
            options={owners.map((o) => o.project)}
            onChange={(v) => update("project", v)}
          />
          <div>
            <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
              port range
            </label>
            <div className="flex items-center gap-1">
              <input
                value={filters.port_min || ""}
                onChange={(e) => update("port_min", e.target.value)}
                placeholder="min"
                className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs font-mono w-20"
              />
              <span className="text-slate-500">—</span>
              <input
                value={filters.port_max || ""}
                onChange={(e) => update("port_max", e.target.value)}
                placeholder="max"
                className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs font-mono w-20"
              />
            </div>
          </div>
          {(filters.state || filters.project || filters.port_min || filters.port_max) && (
            <button
              onClick={() => setParams({})}
              className="text-xs text-slate-400 hover:text-accent ml-2"
            >
              Clear filters
            </button>
          )}
          <div className="text-xs text-slate-500 ml-auto">
            {list.data ? `${list.data.count} matching` : "—"}
          </div>
        </div>
      </div>

      <div className="bg-bg-card border border-bg-hover rounded-lg overflow-hidden">
        <div className="grid grid-cols-12 gap-2 px-3 py-2 text-xs uppercase tracking-wide text-slate-500 border-b border-bg-hover">
          <div className="col-span-2">Port</div>
          <div className="col-span-2">State</div>
          <div className="col-span-2">Owner</div>
          <div className="col-span-2">Process</div>
          <div className="col-span-4">Evidence</div>
        </div>
        {list.isLoading && (
          <div className="p-4 text-sm text-slate-400">Loading…</div>
        )}
        {list.data?.ports?.map((p) => (
          <div
            key={p.port_id}
            className="grid grid-cols-12 gap-2 px-3 py-2 border-b border-bg-card text-sm hover:bg-bg-hover/40"
          >
            <div className="col-span-2 font-mono">
              {p.port}/{p.protocol}
            </div>
            <div className="col-span-2">
              <StatePill value={p.state} />
            </div>
            <div className="col-span-2">
              <Link
                to={`/applications/${encodeURIComponent(p.owner_project)}`}
                className="text-xs text-accent hover:underline"
              >
                {p.owner_project}
              </Link>
            </div>
            <div className="col-span-2 text-xs text-slate-400 truncate">
              {p.process || "—"}
            </div>
            <div className="col-span-4">
              <EvidenceBadges sources={p.evidence_sources} />
            </div>
          </div>
        ))}
        {list.data && list.data.count === 0 && (
          <div className="p-4 text-sm text-slate-400">No ports match.</div>
        )}
      </div>
    </div>
  );
}

function FilterPill({ label, value, options, onChange }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
        {label}
      </label>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        className="bg-bg-base border border-bg-hover rounded px-2 py-1 text-xs"
      >
        <option value="">all</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
