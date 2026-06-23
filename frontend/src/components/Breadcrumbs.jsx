import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

// Hierarchical trail. Each item: { label, to? }. Last item (no `to`) = current.
export default function Breadcrumbs({ items = [] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-zinc-500">
      {items.map((it, i) => (
        <span key={`${it.label}-${i}`} className="flex items-center gap-1 min-w-0">
          {i > 0 && <ChevronRight size={12} className="text-zinc-700 shrink-0" />}
          {it.to ? (
            <Link to={it.to} className="hover:text-accent transition truncate">
              {it.label}
            </Link>
          ) : (
            <span className="text-zinc-300 truncate">{it.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
