const TONES = {
  // generic states
  success: "bg-emerald-500/20 text-emerald-300",
  running: "bg-emerald-500/20 text-emerald-300",
  active: "bg-emerald-500/20 text-emerald-300",
  in_use: "bg-emerald-500/20 text-emerald-300",
  listening: "bg-emerald-500/20 text-emerald-300",
  mounted: "bg-emerald-500/20 text-emerald-300",
  configured: "bg-emerald-500/20 text-emerald-300",
  ok: "bg-emerald-500/20 text-emerald-300",
  // pending-ish
  declared: "bg-amber-500/20 text-amber-300",
  queued: "bg-amber-500/20 text-amber-300",
  pending: "bg-amber-500/20 text-amber-300",
  skipped: "bg-amber-500/20 text-amber-300",
  // failure
  failed: "bg-rose-500/20 text-rose-300",
  refused: "bg-rose-500/20 text-rose-300",
  exited: "bg-rose-500/20 text-rose-300",
  inactive: "bg-slate-500/20 text-slate-300",
  unused: "bg-slate-500/20 text-slate-300",
};

export default function StatePill({ value }) {
  const v = (value || "—").toLowerCase();
  const tone = TONES[v] || "bg-slate-500/20 text-slate-300";
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded ${tone}`}>
      {value || "—"}
    </span>
  );
}
