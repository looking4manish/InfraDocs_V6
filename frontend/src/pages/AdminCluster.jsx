import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpoints } from "../api/client";
import { cn } from "../lib/cn";

// Admin / Cluster tab — the single home for cluster role management. Behind the app's
// admin auth (AuthGate) like every other page. Every control is driven by /api/cluster
// endpoints that carry their own guards; when a transition is blocked we SHOW the reason
// the backend returned rather than silently greying the button out.

function Pill({ tone = "zinc", children }) {
  const tones = {
    zinc: "bg-white/5 text-zinc-300",
    green: "bg-emerald-500/15 text-emerald-300",
    amber: "bg-amber-500/15 text-amber-300",
    rose: "bg-rose-500/15 text-rose-300",
  };
  return <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full", tones[tone])}>{children}</span>;
}

function Section({ title, desc, children }) {
  return (
    <div className="neon-panel rounded-xl p-4 mb-4">
      <div className="text-[13px] text-zinc-200 font-medium">{title}</div>
      {desc && <div className="text-[11.5px] text-zinc-500 mt-0.5">{desc}</div>}
      <div className="mt-3">{children}</div>
    </div>
  );
}

const btn = "text-[12px] px-3 py-1.5 rounded-lg border border-white/10 text-zinc-200 hover:bg-bg-elev disabled:opacity-40 disabled:cursor-not-allowed";
const btnPrimary = "text-[12px] px-3 py-1.5 rounded-lg neon-glow border border-[var(--neon)] bg-[var(--neon)]/10 hover:bg-[var(--neon)]/20 disabled:opacity-40";
const btnDanger = "text-[12px] px-3 py-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20 disabled:opacity-40";
const input = "text-[12px] px-2 py-1.5 rounded-lg bg-bg-card border border-white/10 text-zinc-100 placeholder:text-zinc-600 focus:border-[var(--neon)] outline-none";

export default function AdminCluster() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState(null);
  const flash = (kind, text) => setMsg({ kind, text });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["cluster-state"] });
    qc.invalidateQueries({ queryKey: ["cluster-audit"] });
    qc.invalidateQueries({ queryKey: ["federation-tokens"] });
  };

  const state = useQuery({
    queryKey: ["cluster-state"],
    queryFn: () => endpoints.clusterState().then((r) => r.data),
    refetchInterval: 5000,
  });
  const audit = useQuery({
    queryKey: ["cluster-audit"],
    queryFn: () => endpoints.clusterAudit(50).then((r) => r.data),
    refetchInterval: 10000,
  });
  const tokens = useQuery({
    queryKey: ["federation-tokens"],
    queryFn: () => endpoints.listFederationTokens().then((r) => r.data),
    refetchInterval: 15000,
  });

  const run = (fn, ok) =>
    useMutation({
      mutationFn: fn,
      onSuccess: (d) => {
        if (d && d.ok === false && (d.reason || d.blocked || d.needs_force)) {
          flash("err", d.reason || "blocked");
        } else {
          flash("ok", typeof ok === "function" ? ok(d) : ok);
        }
        refresh();
      },
      onError: (e) => flash("err", e?.response?.data?.detail?.reason || e?.response?.data?.detail || "request failed"),
    });

  const d = state.data;
  const enable = run((v) => endpoints.clusterEnable(v).then((r) => r.data), (r) => `cluster ${r.cluster_enabled ? "enabled" : "disabled"}`);
  const toPrimary = run((p) => endpoints.clusterToPrimary(p).then((r) => r.data), "now serving as primary");
  const join = run((b) => endpoints.clusterJoin(b).then((r) => r.data), "joined the cluster as secondary");
  const promote = run((f) => endpoints.clusterPromote(f).then((r) => r.data), (r) => (r.promoted ? "promoted to primary" : r.reason));
  const demote = run(() => endpoints.clusterDemote().then((r) => r.data), "demoted to secondary");
  const toStandalone = run((b) => endpoints.clusterToStandalone(b.force, b.confirm).then((r) => r.data), "converted to standalone");
  const setPriority = run((p) => endpoints.clusterSetPriority(p).then((r) => r.data), (r) => `priority set to ${r.priority}`);
  const evict = run((b) => endpoints.clusterEvict(b.node_id, b.confirm).then((r) => r.data), (r) => `evicted ${r.evicted} (fleet now ${r.fleet_size})`);
  const overrideMut = run((v) => endpoints.clusterOverride(v).then((r) => r.data), "override updated");
  const mint = run((sid) => endpoints.mintFederationToken(sid).then((r) => r.data), (r) => `token minted for ${r.server_id}`);
  const revoke = run((t) => endpoints.revokeFederationToken(t).then((r) => r.data), "token revoked");

  if (!d) return <div className="text-zinc-500 text-sm">Loading cluster state…</div>;

  const role = d.role;
  const g = d.guards || {};

  return (
    <div className="max-w-5xl">
      <div className="flex items-center gap-2 flex-wrap mb-4">
        <h1 className="text-lg font-semibold text-zinc-100">Admin · Cluster</h1>
        <Pill tone={role === "primary" ? "green" : role === "secondary" ? "zinc" : "amber"}>role: {role}</Pill>
        <Pill tone={d.cluster_enabled ? "green" : "zinc"}>cluster {d.cluster_enabled ? "enabled" : "disabled"}</Pill>
        {d.override && <Pill tone="amber">override pinned</Pill>}
        {!d.majority && <Pill tone="rose">no majority</Pill>}
        <span className="ml-auto text-[11px] text-zinc-500 font-mono">
          {d.node_id} · p{d.priority ?? "—"} · fleet {d.fleet_size} · leader {d.current_leader || "—"}
        </span>
      </div>

      {msg && (
        <div className={cn("text-[12px] mb-4 px-3 py-2 rounded-lg border",
          msg.kind === "ok" ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : "border-rose-500/30 bg-rose-500/10 text-rose-300")}>
          {msg.text}
        </div>
      )}

      {/* cluster_enabled toggle */}
      <Section title="Cluster machinery" desc="Enable starts the gossip/election loop live (no restart). Disable quiesces it — role and roster are kept.">
        <button className={d.cluster_enabled ? btn : btnPrimary}
          disabled={enable.isPending}
          onClick={() => enable.mutate(!d.cluster_enabled)}>
          {d.cluster_enabled ? "Disable cluster (quiesce gossip)" : "Enable cluster (start gossip)"}
        </button>
      </Section>

      {/* role transition matrix — controls appropriate to the current role */}
      <Section title="Role transitions" desc="Each transition is guarded per its real hazard. Blocked controls show why.">
        {role === "standalone" && (
          <div className="flex flex-col gap-4">
            <StandaloneToPrimary onGo={(p) => toPrimary.mutate(p)} busy={toPrimary.isPending} />
            <JoinCluster onGo={(b) => join.mutate(b)} busy={join.isPending} />
          </div>
        )}
        {role === "secondary" && (
          <div className="flex items-center gap-2 flex-wrap">
            <PromoteControl d={d} onPromote={(f) => promote.mutate(f)} busy={promote.isPending} />
          </div>
        )}
        {role === "primary" && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <button className={btn} disabled={!!g.demote_blocked_reason || demote.isPending}
                onClick={() => demote.mutate()}>Demote to secondary</button>
              {g.demote_blocked_reason && <span className="text-[11.5px] text-amber-300">blocked: {g.demote_blocked_reason}</span>}
            </div>
            <PrimaryToStandalone d={d} onGo={(b) => toStandalone.mutate(b)} busy={toStandalone.isPending} />
            <div className="flex items-center gap-2 flex-wrap">
              <button className={btn} disabled={overrideMut.isPending}
                onClick={() => overrideMut.mutate(!d.override)}>
                {d.override ? "Clear override (allow elections)" : "Pin this primary (override)"}
              </button>
            </div>
          </div>
        )}
      </Section>

      {/* priority reassignment */}
      <Section title="Failover priority" desc="1–99, 1 = highest. The primary rejects a number already in use (same rule as install).">
        <PriorityControl current={d.priority} onGo={(p) => setPriority.mutate(p)} busy={setPriority.isPending} />
      </Section>

      {/* roster + evict */}
      <Section title="Fleet roster" desc="Evicting removes a node AND tombstones it so it can't re-gossip back — correctly shrinking the majority-guard denominator.">
        <div className="flex flex-col gap-1">
          {[...(d.nodes || [])].sort((a, b) => (a.priority ?? 99) - (b.priority ?? 99)).map((n) => (
            <div key={n.node_id} className="flex items-center gap-2 text-[12px] py-1 border-b border-white/5">
              <span className={cn("w-1.5 h-1.5 rounded-full", n.reachable ? "bg-emerald-400" : "bg-zinc-600")} />
              <span className="font-mono text-zinc-500 w-8">p{n.priority ?? "—"}</span>
              <span className={cn("font-mono", n.is_primary ? "text-accent-soft" : "text-zinc-200")}>{n.node_id}</span>
              {n.is_primary && <Pill tone="green">primary</Pill>}
              {n.self && <Pill>this node</Pill>}
              <span className="ml-auto text-[10.5px] text-zinc-600">{n.reachable ? "reachable" : "unreachable"}</span>
              {!n.self && <EvictControl nodeId={n.node_id} onGo={(b) => evict.mutate(b)} busy={evict.isPending} />}
            </div>
          ))}
        </div>
      </Section>

      {/* join-token lifecycle */}
      <Section title="Join tokens" desc="A secondary enrolls with a token minted here — the same token store the installer's enroll validates against.">
        <TokenMint onGo={(sid) => mint.mutate(sid)} busy={mint.isPending} />
        <div className="mt-3 flex flex-col gap-1">
          {(tokens.data?.tokens || []).length === 0 && <div className="text-[11.5px] text-zinc-600">no outstanding tokens</div>}
          {(tokens.data?.tokens || []).map((t) => (
            <div key={t.token} className="flex items-center gap-2 text-[12px] py-1 border-b border-white/5">
              <span className="font-mono text-zinc-300">{t.server_id}</span>
              <span className="font-mono text-zinc-600">{t.token_preview}</span>
              <button className={cn(btnDanger, "ml-auto")} disabled={revoke.isPending}
                onClick={() => revoke.mutate(t.token)}>Revoke</button>
            </div>
          ))}
        </div>
      </Section>

      {/* audit trail */}
      <Section title="Audit trail" desc="Every transition — actor, from→to, node, result, reason.">
        <div className="flex flex-col gap-0.5 max-h-[320px] overflow-y-auto">
          {(audit.data?.entries || []).length === 0 && <div className="text-[11.5px] text-zinc-600">no cluster actions yet</div>}
          {(audit.data?.entries || []).map((e, i) => (
            <div key={i} className="flex items-center gap-2 text-[11.5px] py-1 border-b border-white/5">
              <span className="font-mono text-zinc-600 shrink-0">{String(e.ts).replace("T", " ").slice(0, 19)}</span>
              <span className="text-zinc-400">{e.actor}</span>
              <span className="font-mono text-zinc-200">{e.action}</span>
              <span className="text-zinc-500">{e.from_role}→{e.to_role}</span>
              <Pill tone={e.result === "ok" ? "green" : e.result === "refused" ? "rose" : "amber"}>{e.result}</Pill>
              {e.reason && <span className="text-zinc-500 truncate">{e.reason}</span>}
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function StandaloneToPrimary({ onGo, busy }) {
  const [p, setP] = useState(1);
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[12px] text-zinc-300 w-40">Become cluster primary</span>
      <input className={cn(input, "w-20")} type="number" min={1} max={99} value={p}
        onChange={(e) => setP(Number(e.target.value))} placeholder="priority" />
      <button className={btnPrimary} disabled={busy} onClick={() => onGo(p)}>Enable + become primary</button>
    </div>
  );
}

function JoinCluster({ onGo, busy }) {
  const [f, setF] = useState({ primary_url: "", join_token: "", advertise_url: "", priority: 2 });
  const set = (k) => (e) => setF({ ...f, [k]: k === "priority" ? Number(e.target.value) : e.target.value });
  const ready = f.primary_url && f.join_token && f.advertise_url && f.priority;
  return (
    <div className="flex flex-col gap-2 border-t border-white/5 pt-3">
      <span className="text-[12px] text-zinc-300">Join an existing cluster as secondary <span className="text-zinc-600">(reuses the installer's enroll path)</span></span>
      <div className="flex items-center gap-2 flex-wrap">
        <input className={cn(input, "w-64")} placeholder="primary address (http://…:8081)" value={f.primary_url} onChange={set("primary_url")} />
        <input className={cn(input, "w-56")} placeholder="join token" value={f.join_token} onChange={set("join_token")} />
        <input className={cn(input, "w-64")} placeholder="this node's reachable address" value={f.advertise_url} onChange={set("advertise_url")} />
        <input className={cn(input, "w-20")} type="number" min={1} max={99} value={f.priority} onChange={set("priority")} />
        <button className={btnPrimary} disabled={busy || !ready} onClick={() => onGo(f)}>Validate token + join</button>
      </div>
    </div>
  );
}

function PromoteControl({ d, onPromote, busy }) {
  const [needsForce, setNeedsForce] = useState(false);
  // The promote endpoint returns needs_force when peers are unreachable; the parent flash
  // shows the reason. Here we offer force after a first refusal.
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button className={btnPrimary} disabled={busy} onClick={() => { setNeedsForce(true); onPromote(false); }}>
        Promote this node to primary
      </button>
      {needsForce && (
        <button className={btnDanger} disabled={busy} onClick={() => onPromote(true)}>
          Force promote (only if old primary is truly down)
        </button>
      )}
    </div>
  );
}

function PrimaryToStandalone({ d, onGo, busy }) {
  const deps = d.guards?.to_standalone_dependents || [];
  const [confirm, setConfirm] = useState("");
  const need = deps.length > 0;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button className={need ? btnDanger : btn} disabled={busy || (need && confirm !== d.node_id)}
        onClick={() => onGo({ force: need, confirm })}>
        Convert to standalone
      </button>
      {need && (
        <>
          <span className="text-[11.5px] text-amber-300">
            orphans {deps.length} secondary({deps.join(", ")}) — type <span className="font-mono">{d.node_id}</span> to confirm
          </span>
          <input className={cn(input, "w-40")} placeholder={d.node_id} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </>
      )}
    </div>
  );
}

function PriorityControl({ current, onGo, busy }) {
  const [p, setP] = useState(current || 1);
  return (
    <div className="flex items-center gap-2">
      <input className={cn(input, "w-20")} type="number" min={1} max={99} value={p} onChange={(e) => setP(Number(e.target.value))} />
      <button className={btn} disabled={busy} onClick={() => onGo(p)}>Set priority</button>
    </div>
  );
}

function EvictControl({ nodeId, onGo, busy }) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  if (!open) return <button className={cn(btnDanger, "py-1 px-2")} onClick={() => setOpen(true)}>Evict</button>;
  return (
    <span className="flex items-center gap-1.5">
      <input className={cn(input, "w-32 py-1")} placeholder={`type ${nodeId}`} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      <button className={cn(btnDanger, "py-1 px-2")} disabled={busy || confirm !== nodeId}
        onClick={() => onGo({ node_id: nodeId, confirm })}>Confirm</button>
      <button className={cn(btn, "py-1 px-2")} onClick={() => { setOpen(false); setConfirm(""); }}>×</button>
    </span>
  );
}

function TokenMint({ onGo, busy }) {
  const [sid, setSid] = useState("");
  return (
    <div className="flex items-center gap-2">
      <input className={cn(input, "w-56")} placeholder="new secondary's node id" value={sid} onChange={(e) => setSid(e.target.value)} />
      <button className={btn} disabled={busy || !sid} onClick={() => onGo(sid)}>Mint join token</button>
    </div>
  );
}
