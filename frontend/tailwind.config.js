/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // MXH Neon-Depth: deep slate-navy surface ladder; one MongoDB-green signal accent.
        bg: {
          base: "#070d18",
          panel: "#0a1322",
          card: "#0a1626", // solid fallback; glass gradient lives in .neon-panel (index.css)
          elev: "#0f2238",
          hover: "#11263d",
        },
        accent: {
          DEFAULT: "#00ED64",
          dim: "#00c853",
          soft: "#5cf2a0",
        },
        // Strain ramp for load / usage / pressure / hot states.
        strain: {
          lo: "#00ED64",
          mid: "#f59e0b",
          hi: "#ef4444",
        },
        "accent-cyan": "#34d8e8",
        "accent-yellow": "#facc15",
        ink: "#e8eef7",
      },
      fontFamily: {
        sans: ["Geist", "Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
