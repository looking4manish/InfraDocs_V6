import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import { formatBytes } from "../components/Bytes";
import ActionButton from "../components/ActionButton";
import StatePill from "../components/StatePill";

function Section({ title, count, children, right }) {
  return (
    <section className="bg-bg-card border border-bg-hover rounded-lg mb-4">
      <header className="px-4 py-2.5 border-b border-bg-hover flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-sm">{title}</h2>
          {typeof count === "number" && (
            <span className="text-xs text-slate-500">· {count}</span>
          )}
        </div>
        {right}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function KV({ label, value }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="text-sm text-slate-200 break-all">{value ?? "—"}</span>
    </div>
  );
}

function ContainerRow({ name, port_mapping }) {
  const assetId = `oci:container:${name}`;
  // We don't actually have the asset_id without another lookup; use name+lookup via /api/assets.
  // Instead, look up the container asset to get its real asset_id.
  const q = useQuery({
    queryKey: ["asset-by-name", "docker_container", name],
    queryFn: () =>
      endpoints
        .listAssets({ category: "docker_container" })
        .then((r) => r.data.assets.find((a) => a.name === name)),
  });
  const asset = q.data;
  const id = asset?.asset_id || assetId;
  const isSelf = name.startsWith("infradocs-v6-");

  return (
    <div className="flex items-center justify-between py-2 border-b border-bg-hover/40 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-sm text-slate-200 truncate">{name}</span>
        {asset?.status && <StatePill value={asset.status} />}
        {port_mapping && (
          <span className="text-xs text-slate-500 font-mono">
            {port_mapping}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1">
        <ActionButton
          action="logs"
          fire={() => endpoints.fireAssetAction(id, "logs", { tail: 200 })}
          label="logs"
        />
        <ActionButton
          action="restart"
          fire={() => endpoints.fireAssetAction(id, "restart")}
          disabled={isSelf}
          disabledReason="Self-protected — would kill the API"
          invalidateKeys={[["asset-by-name", "docker_container", name]]}
        />
        <ActionButton
          action="stop"
          fire={() => endpoints.fireAssetAction(id, "stop")}
          disabled={isSelf}
          disabledReason="Self-protected — would kill the API"
          invalidateKeys={[["asset-by-name", "docker_container", name]]}
        />
        <ActionButton
          action="start"
          fire={() => endpoints.fireAssetAction(id, "start")}
          invalidateKeys={[["asset-by-name", "docker_container", name]]}
        />
      </div>
    </div>
  );
}

function SystemdRow({ name }) {
  const q = useQuery({
    queryKey: ["asset-by-name", "systemd_service", name],
    queryFn: () =>
      endpoints
        .listAssets({ category: "systemd_service" })
        .then((r) => r.data.assets.find((a) => a.name === name)),
  });
  // Fallback to systemd_timer if not found
  const q2 = useQuery({
    queryKey: ["asset-by-name", "systemd_timer", name],
    queryFn: () =>
      endpoints
        .listAssets({ category: "systemd_timer" })
        .then((r) => r.data.assets.find((a) => a.name === name)),
    enabled: q.isSuccess && !q.data,
  });
  const asset = q.data || q2.data;
  const id = asset?.asset_id || `oci:service:${name}`;
  const isSelf = name.startsWith("infradocs-v6-");

  return (
    <div className="flex items-center justify-between py-2 border-b border-bg-hover/40 last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-sm text-slate-200 truncate">{name}</span>
        {asset?.status && <StatePill value={asset.status} />}
      </div>
      <div className="flex items-center gap-1">
        <ActionButton
          action="status"
          fire={() => endpoints.fireAssetAction(id, "status")}
        />
        <ActionButton
          action="logs"
          fire={() => endpoints.fireAssetAction(id, "logs", { tail: 200 })}
        />
        <ActionButton
          action="restart"
          fire={() => endpoints.fireAssetAction(id, "restart")}
          disabled={isSelf}
          disabledReason="Self-protected — would kill the API"
        />
      </div>
    </div>
  );
}

export default function ApplicationDetail() {
  const { name } = useParams();
  const q = useQuery({
    queryKey: ["application", name],
    queryFn: () => endpoints.getApplication(name).then((r) => r.data),
  });
  const ports = useQuery({
    queryKey: ["ports", { project: name }],
    queryFn: () => endpoints.listPorts({ project: name }).then((r) => r.data),
  });
  const storage = useQuery({
    queryKey: ["storage", { project: name }],
    queryFn: () => endpoints.listStorage({ project: name }).then((r) => r.data),
  });

  const app = q.data;
  const isSystem = app?.type === "system";

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <Link to="/applications" className="text-xs text-slate-400 hover:text-accent">
            ← All applications
          </Link>
          <div className="flex items-center gap-2 mt-1">
            <h1 className="text-xl font-semibold">{name}</h1>
            {app && (
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded ${
                  isSystem
                    ? "bg-slate-500/20 text-slate-300"
                    : "bg-accent/15 text-accent"
                }`}
              >
                {app.type}
              </span>
            )}
            {app?.internet_exposed && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">
                {app.cloudflare ? "via Cloudflare" : "internet-exposed"}
              </span>
            )}
          </div>
        </div>
        {app && app.containers?.length > 0 && (
          <div className="flex items-center gap-2">
            <ActionButton
              action="restart"
              size="sm"
              fire={() => endpoints.fireApplicationAction(name, "restart")}
              label="Restart app"
            />
          </div>
        )}
      </div>

      {q.isLoading && <div className="text-slate-400">Loading…</div>}
      {q.isError && (
        <div className="text-rose-300 text-sm">
          {q.error.response?.status === 404
            ? "No application by that name."
            : `Failed: ${String(q.error)}`}
        </div>
      )}

      {app && (
        <>
          {/* Top-line stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <StatCard label="Components" value={app.components_count ?? 0} />
            <StatCard label="Containers" value={app.containers?.length || 0} />
            <StatCard label="Systemd units" value={app.systemd_units?.length || 0} />
            <StatCard label="Nginx sites" value={app.nginx_sites?.length || 0} />
            <StatCard label="Disk" value={formatBytes(app.total_size_bytes)} />
          </div>

          {/* URLs */}
          {app.urls?.length > 0 && (
            <Section title="URLs" count={app.urls.length}>
              <div className="space-y-1">
                {app.urls.map((u) => (
                  <a
                    key={u}
                    href={u}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-accent hover:underline text-sm break-all"
                  >
                    {u}
                  </a>
                ))}
              </div>
            </Section>
          )}

          {/* Containers */}
          {app.containers?.length > 0 && (
            <Section title="Containers" count={app.containers.length}>
              {app.containers.map((c) => {
                const pm = app.port_mappings?.find(
                  (m) => m.container === c
                );
                return (
                  <ContainerRow
                    key={c}
                    name={c}
                    port_mapping={
                      pm ? `${pm.host_port} → ${pm.container_port}` : null
                    }
                  />
                );
              })}
            </Section>
          )}

          {/* Compose */}
          {app.compose_file && (
            <Section title="Compose">
              <div className="text-sm text-slate-300 font-mono break-all">
                {app.compose_file}
              </div>
            </Section>
          )}

          {/* Systemd */}
          {app.systemd_units?.length > 0 && (
            <Section title="Systemd units" count={app.systemd_units.length}>
              {app.systemd_units.map((u) => (
                <SystemdRow key={u} name={u} />
              ))}
            </Section>
          )}

          {/* Nginx */}
          {app.nginx_sites?.length > 0 && (
            <Section title="Nginx sites" count={app.nginx_sites.length}>
              <div className="space-y-1">
                {app.nginx_sites.map((s) => (
                  <div key={s} className="text-sm text-slate-200">
                    {s}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Volumes */}
          {app.volumes?.length > 0 && (
            <Section title="Docker volumes" count={app.volumes.length}>
              {app.volumes.map((v) => (
                <div
                  key={v.name}
                  className="flex items-center justify-between py-1.5 border-b border-bg-hover/40 last:border-0"
                >
                  <div className="text-sm text-slate-200">{v.name}</div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span className="font-mono truncate max-w-[260px]" title={v.mountpoint}>
                      {v.mountpoint}
                    </span>
                    <span>{formatBytes(v.size_bytes)}</span>
                  </div>
                </div>
              ))}
            </Section>
          )}

          {/* Ports — pulled from the registry, filtered to this owner */}
          {ports.data && ports.data.count > 0 && (
            <Section
              title="Ports"
              count={ports.data.count}
              right={
                <Link
                  to={`/ports?project=${encodeURIComponent(name)}`}
                  className="text-xs text-slate-400 hover:text-accent"
                >
                  View in ports registry →
                </Link>
              }
            >
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
                {ports.data.ports.map((p) => (
                  <div
                    key={p.port_id}
                    className="flex items-center justify-between py-1 text-sm"
                  >
                    <div className="font-mono">
                      {p.port}/{p.protocol}
                    </div>
                    <div className="flex items-center gap-2">
                      <StatePill value={p.state} />
                      <span className="text-xs text-slate-500">
                        {p.process || "—"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Storage — pulled from the registry, filtered to this owner */}
          {storage.data && storage.data.count > 0 && (
            <Section
              title="Storage"
              count={storage.data.count}
              right={
                <Link
                  to={`/storage?project=${encodeURIComponent(name)}`}
                  className="text-xs text-slate-400 hover:text-accent"
                >
                  View in storage registry →
                </Link>
              }
            >
              {storage.data.storage.map((s) => (
                <div
                  key={s.storage_id}
                  className="flex items-center justify-between py-1.5 border-b border-bg-hover/40 last:border-0"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-hover text-slate-400">
                      {s.kind}
                    </span>
                    <span className="text-sm text-slate-200 truncate" title={s.path}>
                      {s.name}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400">
                    {formatBytes(s.size_bytes)}
                  </div>
                </div>
              ))}
            </Section>
          )}

          {/* Env keys */}
          {app.env_keys?.length > 0 && (
            <Section title="Env keys (names only)" count={app.env_keys.length}>
              <div className="flex flex-wrap gap-1">
                {app.env_keys.map((k) => (
                  <span
                    key={k}
                    className="text-[11px] font-mono px-1.5 py-0.5 bg-bg-hover rounded text-slate-300"
                  >
                    {k}
                  </span>
                ))}
              </div>
            </Section>
          )}

          {/* Project dir */}
          {app.project_dir && (
            <Section title="Project directory">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <KV label="Path" value={<span className="font-mono">{app.project_dir}</span>} />
                <KV label="Tree size" value={formatBytes(app.project_dir_size_bytes)} />
                <KV label="Total (incl. volumes)" value={formatBytes(app.total_size_bytes)} />
              </div>
            </Section>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="bg-bg-card border border-bg-hover rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="text-lg font-semibold mt-0.5">{value}</div>
    </div>
  );
}
