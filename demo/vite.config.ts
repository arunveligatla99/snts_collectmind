import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const base = env.VITE_BASE_PATH ?? "/";
  return {
  base,
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api/v1": {
        target: "http://localhost:8081",
        changeOrigin: true,
      },
      "/prom": {
        target: "http://localhost:9090",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/prom/, ""),
      },
    },
  },
  };
});
