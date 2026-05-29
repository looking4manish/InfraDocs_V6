/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Vercel/Geist-style monochrome (zinc). Colour is reserved for status only.
        bg: {
          base: "#09090b",
          panel: "#0e0e11",
          card: "#161619",
          hover: "#27272a",
        },
        accent: {
          DEFAULT: "#fafafa",
          dim: "#d4d4d8",
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
