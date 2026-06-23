import { useDrawer } from "./DrawerProvider";

function statusColor(status) {
  const ok = ["running", "active", "listening", "mounted", "in_use", "configured"];
  if (ok.includes(status)) return "text-emerald-300";
  if (status === "unused" || status === "inactive") return "text-slate-400";
  return "text-rose-300";
}

export default function AssetRow({ asset }) {
  const { openDrawer } = useDrawer();
  const open = () =>
    openDrawer({ type: "asset", id: asset.asset_id, label: asset.name });
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      }}
      className="grid grid-cols-12 gap-3 py-2 px-3 border-b border-bg-card hover:bg-bg-hover/40 text-sm cursor-pointer outline-none focus-visible:bg-bg-hover/40 focus-visible:ring-1 focus-visible:ring-accent/40 transition-colors"
    >
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
