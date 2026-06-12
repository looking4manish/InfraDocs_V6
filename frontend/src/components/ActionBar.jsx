import { useState, useRef, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";
import { CARD_REGISTRY, ACTION_META, actionsFor, isDestructive } from "../registry/cards";
import { useAllowedActions } from "../hooks/useAllowedActions";
import { endpoints } from "../api/client";
import ActionButton from "./ActionButton";
import { cn } from "../lib/cn";

// The single action surface every card shape consumes.
// entity: { category, asset_id?, name, resolveByName? }
// ALL hooks run unconditionally at the top (React rules of hooks); early
// returns only AFTER every hook has been called.
export default function ActionBar({ entity, className = "", size = "xs", alwaysOpen = false }) {
  const { allowed, destructive } = useAllowedActions();
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useLayoutEffect(() => {
    if ((open || alwaysOpen) && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      // menu is ~140px wide; right-align it under the button.
      setPos({ top: r.bottom + 6, left: r.right - 140 });
    }
  }, [open, alwaysOpen]);

  const category = entity?.category;

  // Resolve asset_id by name when asked. Hook is always called; `enabled`
  // gates the actual fetch so it's cheap when not needed.
  const byName = useQuery({
    queryKey: ["asset-by-name", category, entity?.name],
    queryFn: () =>
      endpoints.listAssets({ category }).then((r) =>
        (r.data.assets || []).find((a) => a.name === entity?.name)
      ),
    enabled: Boolean(entity && !entity.asset_id && entity.resolveByName && category),
  });

  // ---- derived (no hooks below this line) ----
  const reg = category ? CARD_REGISTRY[category] : null;
  const acts = reg ? actionsFor(category, allowed) : [];

  if (!reg || acts.length === 0) return null;

  const id = entity.asset_id || byName.data?.asset_id || `${category}:${entity.name}`;
  const isSelf = (entity.name || "").startsWith("infradocs-v6-");

  const primary = acts.includes(reg.primary) ? reg.primary : acts[0];
  const rest = acts.filter((a) => a !== primary);

  const fire = (action) => {
    const args = action === "logs" ? { tail: 200 } : {};
    return endpoints.fireAssetAction(id, action, args);
  };

  const renderBtn = (action) => {
    const meta = ACTION_META[action] || { label: action };
    const destructiveAct = isDestructive(category, action, destructive);
    const selfBlocked = isSelf && destructiveAct;
    return (
      <ActionButton
        key={action}
        action={action}
        label={meta.label}
        size={size}
        fire={() => fire(action)}
        disabled={selfBlocked}
        disabledReason={selfBlocked ? "Self-protected — would affect the API" : ""}
        invalidateKeys={[["asset-by-name", category, entity.name]]}
      />
    );
  };

  return (
    <div className={cn("inline-flex items-center gap-1", className)}>
      {renderBtn(primary)}
      {rest.length > 0 && (
        <>
          <button
            ref={btnRef}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((v) => !v); }}
            className="inline-flex items-center justify-center w-6 h-6 rounded-md border border-bg-hover text-zinc-400 hover:text-zinc-100 hover:bg-bg-elev transition"
            title="More actions"
          >
            <MoreHorizontal size={14} />
          </button>
          {(open || alwaysOpen) &&
            createPortal(
              <>
                <div
                  className="fixed inset-0 z-[60]"
                  onClick={(e) => { e.stopPropagation(); setOpen(false); }}
                />
                <div
                  className="fixed z-[61] flex flex-col gap-1 p-1.5 rounded-lg border border-bg-hover bg-bg-panel shadow-2xl min-w-[140px]"
                  style={{ top: pos.top, left: pos.left }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {rest.map(renderBtn)}
                </div>
              </>,
              document.body
            )}
        </>
      )}
    </div>
  );
}
