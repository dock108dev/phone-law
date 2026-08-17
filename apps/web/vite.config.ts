import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ["web", "localhost"],
    strictPort: true,
  },
  preview: {
    allowedHosts: ["web", "localhost"],
    strictPort: true,
  },
});
