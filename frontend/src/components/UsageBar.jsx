export default function UsageBar({ percent }) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  // Strain ramp: green -> amber -> red as load/pressure rises.
  const tone =
    p >= 90 ? "strain-hi"
    : p >= 75 ? "strain-mid"
    : "strain-lo";
  return (
    <div className="w-full">
      <div className="h-1.5 bg-bg-hover rounded overflow-hidden">
        <div className={`h-full rounded ${tone}`} style={{ width: `${p}%` }} />
      </div>
      <div className="text-[10px] text-slate-500 mt-0.5">{p}%</div>
    </div>
  );
}
