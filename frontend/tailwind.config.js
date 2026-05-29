/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Dark + dense, EaseOut-style. Elevated neutral surfaces; one violet accent.
        bg: {
          base: "#0a0a0c",
          panel: "#0f0f12",
          card: "#16161a",
          elev: "#1c1c21",
          hover: "#26262b",
        },
        accent: {
          DEFAULT: "#8b5cf6",
          dim: "#7c3aed",
          soft: "#a78bfa",
        },
      },
      fontFamily: {
        sans: ["Geist", "Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};