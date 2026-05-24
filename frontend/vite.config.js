import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Don't put bundles under dist/assets — that path shadows the SPA's
    // /assets route (nginx serves the real dir, returns 301 to /assets/,
    // then 403). Using `static` keeps the URL space free for routing.
    assetsDir: "static",
  },
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8004",
        changeOrigin: true,
      },
    },
  },
});
