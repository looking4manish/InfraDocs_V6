import { useEffect, useState } from "react";
import { Palette } from "lucide-react";

// Cycles the switchable neon glow hue (--neon). Persisted to localStorage and
// applied on the document root, so every .neon-* surface recolors instantly.
const NEON_THEMES = [
  { name: "Cyan", color: "#34d8e8" },
  { name: "Green", color: "#00ED64" },
  { name: "Yellow", color: "#facc15" },
  { name: "Violet", color: "#a78bfa" },
  { name: "Rose", color: "#fb7185" },
  { name: "White", color: "#e8eef7" },
];

export default function ThemeSwitcher() {
  const [i, setI] = useState(() => {
    const saved = localStorage.getItem("ifd_neon");
    const idx = NEON_THEMES.findIndex((t) => t.color === saved);
    return idx >= 0 ? idx : 0;
  });

  useEffect(() => {
    const t = NEON_THEMES[i];
    document.documentElement.style.setProperty("--neon", t.color);
    localStorage.setItem("ifd_neon", t.color);
  }, [i]);

  const t = NEON_THEMES[i];
  return (
    <button
      onClick={() => setI((n) => (n + 1) % NEON_THEMES.length)}
      title={`Neon theme: ${t.name} — click to cycle`}
      aria-label={`Neon theme: ${t.name}. Click to change.`}
      className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-bg-hover hover:bg-bg-elev transition"
      style={{ boxShadow: `inset 0 0 10px -3px ${t.color}, 0 0 8px -4px ${t.color}` }}
    >
      <Palette size={15} style={{ color: t.color }} />
    </button>
  );
}
