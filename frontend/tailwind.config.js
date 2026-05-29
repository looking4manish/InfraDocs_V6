/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Pure-black canvas with an elevated neutral surface ladder; one violet accent.
        bg: {
          base: "#000000",
          panel: "#0a0a0c",
          card: "#121214",
          elev: "#19191d",
          hover: "#242429",
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
