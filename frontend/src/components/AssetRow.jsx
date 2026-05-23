function statusColor(status) {
  const ok = ["running", "active", "listening", "mounted", "in_use", "configured"];
  if (ok.includes(status)) return "text-emerald-300";
  if (status === "unused" || status === "inactive") return "text-slate-400";
  return "text-rose-300";
}

export default function AssetRow({ asset }) {
  return (
    <div className="grid grid-cols-12 gap-3 py-2 px-3 border-b border-bg-card hover:bg-bg-hover/40 text-sm">
      <div className="col-span-4 truncate" title={asset.name}>
        {asset.name}
      </div>
      <div className="col-span-3 text-xs text-slate-400">
        {asset.category.replace(/_/g, " ")}
      </div>
      <div className={`col-span-2 text-xs ${statusColor(asset.status)}`}>
        {asset.status}
      </div>
      <div className="col-span-3 text-xs text-slate-400 truncate">
        {asset.project}
      </div>
    </div>
  );
}
