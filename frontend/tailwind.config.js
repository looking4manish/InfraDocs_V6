/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // V5-style dark palette
        bg: {
          base: "#0b1220",
          panel: "#111a2e",
          card: "#16213e",
          hover: "#1c2a4a",
        },
        accent: {
          DEFAULT: "#3b82f6",
          dim: "#1e40af",
        },
      },
    },
  },
  plugins: [],
};
