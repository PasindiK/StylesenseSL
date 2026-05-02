import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://localhost:8003";

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
    hmr: {
      host: "localhost",
      port: 5173,
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