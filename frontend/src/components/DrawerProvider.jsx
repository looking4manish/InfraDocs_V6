import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import {
  X, Boxes, Container, Globe, Plug, HardDrive, Cog, ShieldCheck,
  ShieldAlert, Link2, CircleDot, TriangleAlert,
} from "lucide-react";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";
import ActionBar from "./ActionBar";

const DrawerCtx = createContext({ openDrawer: () => {}, closeDrawer: () => {} });
export const useDrawer = () => useContext(DrawerCtx);

const KIND_ICON = {
  docker_container: Container, docker_image: Boxes, docker_volume: HardDrive,
  docker_network: Plug, nginx_server_block: Globe, systemd_service: Cog,
  systemd_timer: Cog, network_port: Plug, storage_mount: HardDrive,
};

function Pill({ tone = "zinc", children }) {
  const tones = {
    zinc: "bg-white/[0.05] text-zinc-400",
    violet: "bg-accent/15 text-accent-soft",
    green: "bg-emerald-500/10 text-emerald-400",
    amber: "bg-amber-500/10 text-amber-400",
    red: "bg-red-500/10 text-red-400",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium", tones[tone])}>
      {children}
    </span>
  );
}

function Section({ title, children }) {
  return (
    <div className="mt-5">
      <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-zinc-600 mb-2">{title}</div>
      {children}
    </div>
  );
}

function Row({ children, className }) {
  return (
    <div className={cn("flex items-center gap-2.5 px-3 py-2 rounded-lg bg-bg-card border border-bg-hover/60 text-[13px]", className)}>
      {children}
    </div>
  );
}

function ApplicationBody({ name }) {
  const q = useQuery({
    queryKey: ["application", name],
    queryFn: () => endpoints.getApplication(name).then((r) => r.data),
  });
  if (q.isLoading)
    return <div className="p-6 text-sm text-zinc-500 animate-pulse">Loading {name}…</div>;
  if (q.isError)
    return <div className="p-6 text-sm text-red-400">Failed to load {name}.</div>;
  const a = q.data;
  const links = a.links || [];
  return (
    <div className="px-5 pb-8">
      <div className="flex flex-wrap items-center gap-2 mt-1">
        <Pill tone="violet">{a.type}</Pill>
        {a.internet_exposed && <Pill tone="amber"><Globe size={11} /> exposed</Pill>}
        {a.resilience?.reboot_safe
          ? <Pill tone="green"><ShieldCheck size={11} /> reboot safe</Pill>
          : <Pill tone="red"><ShieldAlert size={11} /> fragile</Pill>}
      </div>

      {(a.urls || []).length > 0 && (
        <Section title="urls">
          {a.urls.map((u) => (
            <a key={u} href={u} target="_blank" rel="noreferrer"
               className="block text-[13px] text-accent-soft hover:text-accent transition truncate">{u}</a>
          ))}
        </Section>
      )}

      {(a.containers_detail || []).length > 0 && (
        <Section title="containers">
          <div className="space-y-1.5">
            {a.containers_detail.map((c) => (
              <div key={c.name} className="rounded-lg bg-bg-card border border-bg-hover/60 px-3 py-2">
                <div className="flex items-center gap-2.5 text-[13px]">
                  <CircleDot size={13} className={c.running ? "text-emerald-400" : "text-red-400"} />
                  <span className="font-mono text-zinc-200 truncate">{c.name}</span>
                  <span className="ml-auto flex items-center gap-1.5 shrink-0">
                    {c.restart_policy && <Pill>{c.restart_policy}</Pill>}
                    {(c.host_ports || []).map((p) => <Pill key={p} tone="violet">:{p}</Pill>)}
                  </span>
                </div>
                <div className="mt-2">
                  <ActionBar entity={{ category: "docker_container", name: c.name, resolveByName: true }} size="xs" />
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {(a.nginx_detail || []).length > 0 && (
        <Section title="nginx">
          <div className="space-y-1.5">
            {a.nginx_detail.map((n, i) => (
              <Row key={i}>
                <Globe size={13} className="text-zinc-500" />
                <span className="font-mono text-zinc-200 truncate">{n.server_name}</span>
                <span className="ml-auto flex items-center gap-1.5">
                  {(n.listen_ports || []).map((p) => <Pill key={p}>:{p}</Pill>)}
                  {n.upstream_port && <Pill tone="violet">→ :{n.upstream_port}</Pill>}
                  {n.has_ssl && <Pill tone="green">ssl</Pill>}
                </span>
              </Row>
            ))}
          </div>
        </Section>
      )}

      <Section title={`link evidence · ${links.length}`}>
        {links.length === 0 ? (
          <Row className="border-amber-500/30">
            <TriangleAlert size={13} className="text-amber-400" />
            <span className="text-amber-300/90">No linking evidence found</span>
          </Row>
        ) : (
          <div className="space-y-1.5">
            {links.map((l, i) => {
              const Icon = KIND_ICON[l.src_kind] || Link2;
              return (
                <Row key={i}>
                  <Icon size={13} className="text-zinc-500 shrink-0" />
                  <span className="font-mono text-zinc-300 truncate">{l.src}</span>
                  <span className="ml-auto flex items-center gap-1.5 shrink-0">
                    <Pill tone="violet">{l.via}</Pill>
                    <span className="text-[10px] text-zinc-600 font-mono">p{l.pass}</span>
                  </span>
                </Row>
              );
            })}
          </div>
        )}
      </Section>

      {((a.hygiene?.exited_restart_always || []).length > 0 ||
        (a.hygiene?.orphaned_volumes || []).length > 0 ||
        (a.hygiene?.dangling_images || []).length > 0) && (
        <Section title="hygiene">
          <div className="space-y-1.5">
            {(a.hygiene.exited_restart_always || []).map((c) => (
              <Row key={c} className="border-amber-500/30">
                <TriangleAlert size={13} className="text-amber-400" />
                <span className="text-amber-300/90 truncate">{c} exited despite restart=always</span>
              </Row>
            ))}
            {(a.hygiene.orphaned_volumes || []).map((v) => (
              <Row key={v}><HardDrive size={13} className="text-zinc-500" />
                <span className="text-zinc-300 truncate">orphaned volume {v}</span></Row>
            ))}
            {(a.hygiene.dangling_images || []).map((im) => (
              <Row key={im}><Boxes size={13} className="text-zinc-500" />
                <span className="text-zinc-300 truncate">dangling image {im}</span></Row>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function AssetBody({ id }) {
  const q = useQuery({
    queryKey: ["asset", id],
    queryFn: () => endpoints.getAsset(id).then((r) => r.data),
  });
  if (q.isLoading)
    return <div className="p-6 text-sm text-zinc-500 animate-pulse">Loading…</div>;
  if (q.isError)
    return <div className="p-6 text-sm text-red-400">Failed to load asset.</div>;
  const a = q.data;
  return (
    <div className="px-5 pb-8">
      <div className="flex flex-wrap items-center gap-2 mt-1">
        <Pill tone="violet">{a.category}</Pill>
        {a.project && <Pill>{a.project}</Pill>}
      </div>
      <div className="mt-3">
        <ActionBar
          entity={{ category: a.category, asset_id: a.asset_id || id, name: a.name }}
          size="sm"
        />
      </div>
      <Section title="metadata">
        <pre className="text-[11.5px] leading-relaxed font-mono text-zinc-400 bg-bg-card border border-bg-hover/60 rounded-lg p-3 overflow-x-auto">
{JSON.stringify(a.metadata ?? a, null, 2)}
        </pre>
      </Section>
    </div>
  );
}

// Serialize a drawer target into the `?d=` URL token, and back. This makes
// every drawer deep-linkable, shareable, and closeable via the browser Back
// button. Rich fields (label) are kept in component state when available;
// a cold deep-link reconstructs a minimal target the bodies can still load.
function targetToToken(t) {
  if (!t) return null;
  return t.type === "application" ? `app:${t.name}` : `asset:${t.id}`;
}
function tokenToTarget(token) {
  if (!token) return null;
  const i = token.indexOf(":");
  if (i < 0) return null;
  const kind = token.slice(0, i);
  const val = token.slice(i + 1);
  if (kind === "app") return { type: "application", name: val };
  if (kind === "asset") return { type: "asset", id: val, label: val };
  return null;
}

export default function DrawerProvider({ children }) {
  const [params, setParams] = useSearchParams();
  // `rich` holds the in-memory target (with label etc.) set by openDrawer.
  const [rich, setRich] = useState(null);
  const token = params.get("d");
  // Effective target is derived in render: prefer the rich target when it still
  // matches the URL token; otherwise reconstruct a minimal one from the token
  // (cold deep-link or Back/Forward). Pure derivation — no effect, no cascade.
  const target = targetToToken(rich) === token ? rich : tokenToTarget(token);

  const openDrawer = useCallback((t) => {
    setRich(t);
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("d", targetToToken(t));
      return next;
    });
  }, [setParams]);

  const closeDrawer = useCallback(() => {
    setRich(null);
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("d");
      return next;
    });
  }, [setParams]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") closeDrawer(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeDrawer]);

  return (
    <DrawerCtx.Provider value={{ openDrawer, closeDrawer }}>
      {children}
      <AnimatePresence>
        {target && (
          <>
            <motion.div
              key="ifd-drawer-bg"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.16 }}
              onClick={closeDrawer}
              className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px]"
            />
            <motion.aside
              key="ifd-drawer"
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 380, damping: 38 }}
              className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-[440px] bg-bg-panel border-l border-bg-hover shadow-2xl overflow-y-auto"
            >
              <div className="sticky top-0 z-10 flex items-center gap-3 px-5 h-14 bg-bg-panel/95 backdrop-blur border-b border-bg-hover">
                <span className="text-[15px] font-semibold text-zinc-50 truncate">
                  {target.type === "application" ? target.name : target.label || "Asset"}
                </span>
                <button onClick={closeDrawer} aria-label="Close"
                        className="ml-auto p-1.5 rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.06] transition">
                  <X size={16} />
                </button>
              </div>
              {target.type === "application"
                ? <ApplicationBody name={target.name} />
                : <AssetBody id={target.id} />}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </DrawerCtx.Provider>
  );
}
