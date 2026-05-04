import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ["react", "react-dom"],
    alias: {
      react: path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    hmr: {
      host: "127.0.0.1",
      port: 5175,
      protocol: "ws",
    },
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
