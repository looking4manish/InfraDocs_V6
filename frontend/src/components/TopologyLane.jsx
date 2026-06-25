import { motion, useReducedMotion } from "motion/react";
import { Globe, Server, Plug, Box, HardDrive, ShieldCheck, ShieldAlert, Activity, Link2 } from "lucide-react";
import ActionBar from "./ActionBar";
import { cn } from "../lib/cn";
import { formatBytes } from "./Bytes";

const SPRING = { type: "spring", stiffness: 400, damping: 36 };

function rowVariants(reduce) {
  return { hidden: {}, show: { transition: { staggerChildren: reduce ? 0 : 0.045 } } };
}
function itemVariants(reduce) {
  return reduce
    ? { hidden: { opacity: 1, y: 0 }, show: { opacity: 1, y: 0 } }
    : { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: SPRING } };
}

// Pick the authoritative nginx block for a server_name: prefer one that actually
// proxies somewhere (has upstream_port) and/or carries the real url. The :80
// redirect block (upstream_port null) is the weak twin — never the lane node.
function strongestNginx(nginx_detail = []) {
  if (!nginx_detail.length) return null;
  const scored = [...nginx_detail].sort((a, b) => {
    const s = (n) =>
      (n.upstream_port ? 4 : 0) +
      (n.url ? 2 : 0) +
      (n.internet_exposed ? 1 : 0);
    return s(b) - s(a);
  });
  return scored[0];
}

function Node({ icon: Icon, kind, title, children, state, dashed, reduce }) {
  return (
    <motion.div
      variants={itemVariants(reduce)}
      whileHover={reduce ? undefined : { y: -3 }}
      transition={SPRING}
      className={cn(
        "flex-none w-[188px] rounded-[13px] p-3.5",
        dashed
          ? "bg-bg-card border border-dashed border-amber-500/30"
          : "neon-panel hover:bg-bg-elev"
      )}
    >
      <div className="flex items-center gap-1.5 mb-2">
        <Icon size={15} className={dashed ? "text-amber-400/80" : "text-accent-soft"} />
        <span className="text-[10px] uppercase tracking-[0.09em] text-zinc-600 font-medium">
          {kind}
        </span>
      </div>
      <div className="text-[13.5px] font-semibold leading-snug break-all">{title}</div>
      {children && (
        <div className="mt-1.5 flex flex-col gap-0.5 text-[11.5px] text-zinc-500">
          {children}
        </div>
      )}
      {state}
    </motion.div>
  );
}

function StatePill({ running }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 mt-2 w-fit rounded-md px-1.5 py-0.5 text-[10.5px] font-semibold",
        running
          ? "bg-emerald-500/15 text-emerald-300"
          : "bg-rose-500/15 text-rose-300"
      )}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {running ? "running" : "exited"}
    </span>
  );
}

function Connector({ label, dashed, reduce }) {
  return (
    <motion.div variants={itemVariants(reduce)} className="flex-none w-[72px] flex flex-col items-center justify-center gap-1.5 pt-7">
      <span
        className={cn(
          "text-[9.5px] rounded px-1.5 py-px whitespace-nowrap border",
          dashed
            ? "text-amber-400 bg-amber-500/[0.08] border-amber-500/25"
            : "text-accent-soft bg-accent/10 border-accent/25"
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "relative w-full h-px",
          dashed
            ? "border-t-2 border-dashed border-amber-500/40"
            : "bg-gradient-to-r from-accent/20 to-accent/60"
        )}
      >
        <span
          className={cn(
            "absolute -right-px -top-[3px] w-0 h-0 border-y-4 border-y-transparent border-l-[6px]",
            dashed ? "border-l-amber-400" : "border-l-accent"
          )}
        />
      </span>
    </motion.div>
  );
}

export default function TopologyLane({ app, storage }) {
  const reduce = useReducedMotion();
  const nginx = strongestNginx(app?.nginx_detail);
  const upstreamPort = nginx?.upstream_port ?? null;
  const url = nginx?.url || app?.urls?.[0] || null;

  const containers = app?.containers_detail || [];
  // Bind the container by the upstream port living in its host_ports[].
  const container =
    (upstreamPort != null &&
      containers.find((c) => (c.host_ports || []).includes(upstreamPort))) ||
    containers[0] ||
    null;

  const volumes = storage?.storage || [];

  if (!nginx && !container) {
    const units = app?.systemd_units?.length || 0;
    if (units > 0) {
      // Systemd-only service (e.g. a backup unit) — genuinely has no web/container
      // flow, so don't imply the scan failed.
      return (
        <div className="text-[12.5px] text-zinc-400 bg-white/[0.02] border border-white/10 rounded-xl px-4 py-3">
          Runs as {units} systemd unit{units > 1 ? "s" : ""} — no web or container flow to map.
        </div>
      );
    }
    return (
      <div className="text-[12.5px] text-amber-300/90 bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
        No topology evidence yet — no nginx or container detail. Trigger a scan to populate the lane.
      </div>
    );
  }

  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.09em] text-zinc-600 font-medium mb-3">
        Topology
      </div>

      <motion.div
        variants={rowVariants(reduce)}
        initial="hidden"
        animate="show"
        className="flex items-stretch overflow-x-auto pb-2.5 pt-1"
      >
        {url && (
          <>
            <Node icon={Globe} kind="URL" title={url.replace(/^https?:\/\//, "")} reduce={reduce}>
              <span>
                <span className="text-zinc-600">scheme</span>{" "}
                {url.startsWith("https") ? "https" : "http"}
              </span>
            </Node>
            <Connector label={nginx?.cloudflare_origin ? "cloudflare" : "tls"} reduce={reduce} />
          </>
        )}

        {nginx && (
          <>
            <Node
              icon={Server}
              kind="Nginx"
              title={nginx.server_name}
              reduce={reduce}
              state={
                <div className="flex flex-col gap-2 mt-2">
                  {nginx.internet_exposed && (
                    <span className="inline-flex items-center gap-1 text-[10.5px] text-emerald-300/90">
                      <Globe size={11} /> internet-exposed
                    </span>
                  )}
                  <ActionBar
                    entity={{ category: "nginx_server_block", name: nginx.server_name, resolveByName: true }}
                  />
                </div>
              }
            >
              <span>
                <span className="text-zinc-600">listen</span>{" "}
                {(nginx.listen_ports || []).join(" · ")}
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="text-zinc-600">ssl</span>
                {nginx.has_ssl ? (
                  nginx.ssl_not_after ? (
                    <>
                      <ShieldCheck size={11} className="text-emerald-400/80" />
                      {nginx.ssl_not_after.slice(0, 10)}
                    </>
                  ) : (
                    <>
                      <ShieldAlert size={11} className="text-amber-400/80" />
                      <span className="text-amber-400/90">unparsed</span>
                    </>
                  )
                ) : (
                  "—"
                )}
              </span>
            </Node>
            {upstreamPort != null && (
              <Connector label={`proxy_pass :${upstreamPort}`} reduce={reduce} />
            )}
          </>
        )}

        {upstreamPort != null && (
          <>
            <Node icon={Plug} kind="Host port" title={`:${upstreamPort}`} reduce={reduce}>
              <span>
                <span className="text-zinc-600">upstream</span>{" "}
                {nginx?.upstream_host || "localhost"}
              </span>
            </Node>
            {container && <Connector label={`host_port:${upstreamPort}`} reduce={reduce} />}
          </>
        )}

        {container && (
          <Node
            icon={Box}
            kind="Container"
            title={container.name}
            reduce={reduce}
            state={
              <div className="flex flex-col gap-2 mt-2">
                <StatePill running={container.running} />
                <ActionBar
                  entity={{ category: "docker_container", name: container.name, resolveByName: true }}
                />
              </div>
            }
          >
            <span className="break-all">
              <span className="text-zinc-600">image</span>{" "}
              {container.image?.split("/").pop()}
            </span>
            <span>
              <span className="text-zinc-600">restart</span>{" "}
              {typeof container.restart_policy === "string"
                ? container.restart_policy
                : container.restart_policy?.Name || "—"}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="text-zinc-600">health</span>
              {container.has_health_check ? (
                <>
                  <Activity size={11} className="text-emerald-400/70" /> check defined
                </>
              ) : (
                "none"
              )}
            </span>
          </Node>
        )}
      </motion.div>

      {volumes.length > 0 && (
        <>
          <div className="text-[10px] uppercase tracking-[0.09em] text-zinc-600 font-medium mt-4 mb-3">
            Storage
          </div>
          <motion.div
            variants={rowVariants(reduce)}
            initial="hidden"
            animate="show"
            className="flex items-stretch overflow-x-auto pb-2.5 pt-1 gap-3"
          >
            {volumes.map((v) => (
              <Node
                key={v.storage_id || v.name}
                icon={HardDrive}
                kind={v.kind || "volume"}
                title={v.name}
                reduce={reduce}
              >
                <span className="font-mono text-[10.5px] text-zinc-600 break-all">
                  {v.path || v.mountpoint}
                </span>
                <span>
                  <span className="text-zinc-600">size</span>{" "}
                  {formatBytes(v.size_bytes)}
                </span>
              </Node>
            ))}
          </motion.div>
        </>
      )}

      <LinkEvidence links={app?.links || []} />
    </div>
  );
}

function LinkEvidence({ links }) {
  const reduce = useReducedMotion();
  if (!links.length) return null;
  return (
    <motion.div
      variants={{ hidden: {}, show: { transition: { staggerChildren: reduce ? 0 : 0.035 } } }}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-60px" }}
      className="neon-panel rounded-[13px] mt-5 overflow-hidden"
    >
      <div className="flex items-center gap-1.5 px-4 py-3 border-b border-bg-hover">
        <Link2 size={13} className="text-zinc-600" />
        <span className="text-[11px] uppercase tracking-[0.08em] text-zinc-600 font-semibold">
          Link evidence · {links.length} joins
        </span>
      </div>
      {links.map((l, i) => {
        const weak = l.via === "project_tag";
        return (
          <motion.div
            key={i}
            variants={reduce
              ? { hidden: { opacity: 1, y: 0 }, show: { opacity: 1, y: 0 } }
              : { hidden: { opacity: 0, y: 6 }, show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 400, damping: 36 } } }}
            className="grid grid-cols-[140px_1fr_70px] gap-3.5 items-center px-4 py-2 border-b border-bg-hover/40 last:border-0 hover:bg-bg-elev text-[12.5px]"
          >
            <span
              className={cn(
                "font-mono truncate",
                weak ? "text-zinc-600" : "text-accent-soft"
              )}
              title={weak ? "weaker evidence — superseded by upstream_port link" : l.via}
            >
              {l.via}
            </span>
            <span className="text-zinc-500 truncate">
              <b className="text-zinc-300 font-medium">{l.src_kind}</b>{" "}
              {l.src} → <b className="text-zinc-300 font-medium">{l.dst_kind}</b>{" "}
              {l.dst}
            </span>
            <span className="justify-self-end text-zinc-600 text-[10.5px] uppercase tracking-wide">
              pass {l.pass}
            </span>
          </motion.div>
        );
      })}
    </motion.div>
  );
}
