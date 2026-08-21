import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    allowedHosts: ["web", "localhost"],
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://api:8000",
        changeOrigin: false,
      },
    },
  },
  preview: {
    allowedHosts: ["web", "localhost"],
    strictPort: true,
  },
});
