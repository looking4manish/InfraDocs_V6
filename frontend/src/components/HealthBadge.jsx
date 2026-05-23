export default function HealthBadge({ score }) {
  const tone =
    score >= 90 ? "bg-emerald-500/20 text-emerald-300"
    : score >= 70 ? "bg-amber-500/20 text-amber-300"
    : "bg-rose-500/20 text-rose-300";
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${tone}`}>
      {score}
    </span>
  );
}
