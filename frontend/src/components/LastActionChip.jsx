
import { useQuery } from "@tanstack/react-query";

import { endpoints } from "../api/client";

import { cn } from "../lib/cn";



// Tiny "last action" status chip. Reads the most recent action for an asset

// from the audit log (/api/actions/?asset_id=&limit=1). Renders nothing until

// there is at least one logged action. Presentation only.

function rel(ts) {

  if (!ts) return "";

  const then = new Date(ts.endsWith("Z") ? ts : ts + "Z").getTime();

  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));

  if (s < 60) return `${s}s ago`;

  const m = Math.floor(s / 60);

  if (m < 60) return `${m}m ago`;

  const h = Math.floor(m / 60);

  if (h < 24) return `${h}h ago`;

  return `${Math.floor(h / 24)}d ago`;

}



export default function LastActionChip({ assetId, className = "" }) {

  const { data } = useQuery({

    queryKey: ["last-action", assetId],

    queryFn: () =>

      endpoints.listActions({ asset_id: assetId, limit: 1 }).then(

        (r) => (r.data.actions || [])[0] || null

      ),

    enabled: Boolean(assetId),

    staleTime: 15000,

  });

  if (!data) return null;



  const failed = data.status === "failed" || data.refused_reason;

  return (

    <span

      className={cn(

        "inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border",

        failed

          ? "bg-rose-500/10 text-rose-300 border-rose-500/20"

          : "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",

        className

      )}

      title={`${data.action} → ${data.refused_reason || data.status}${

        data.actor ? " by " + data.actor : ""

      }`}

    >

      <span className="font-medium">{data.action}</span>

      <span className="opacity-60">{rel(data.timestamp)}</span>

    </span>

  );

}

