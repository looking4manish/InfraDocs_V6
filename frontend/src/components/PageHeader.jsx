// Shared page shell header: title + subtitle + a glowing summary-stat strip +
// an optional actions slot. Gives every page the Dashboard's structure/identity
// instead of a bare title over an empty canvas.
//
//   <PageHeader title="Assets" subtitle="…" stats={[{label,value,tone?}]} right={<button/>} />
export default function PageHeader({ title, subtitle, stats = [], right }) {
  return (
    <div className="mb-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="text-[13px] text-zinc-500 mt-1">{subtitle}</p>}
        </div>
        {right && <div className="shrink-0">{right}</div>}
      </div>
      {stats.length > 0 && (
        <div className="flex flex-wrap gap-2.5 mt-4">
          {stats.map((s) => (
            <div key={s.label} className="neon-panel rounded-xl px-3.5 py-2 min-w-[112px]">
              <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-500">
                {s.label}
              </div>
              <div
                className="text-[18px] font-semibold tabular-nums mt-0.5 leading-none"
                style={s.tone ? { color: s.tone } : undefined}
              >
                {s.value}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
