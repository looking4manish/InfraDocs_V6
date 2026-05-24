export default function UsageBar({ percent }) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  const tone =
    p >= 90 ? "bg-rose-400"
    : p >= 75 ? "bg-amber-400"
    : "bg-emerald-400";
  return (
    <div className="w-full">
      <div className="h-1.5 bg-bg-hover rounded overflow-hidden">
        <div className={`h-full ${tone}`} style={{ width: `${p}%` }} />
      </div>
      <div className="text-[10px] text-slate-500 mt-0.5">{p}%</div>
    </div>
  );
}
