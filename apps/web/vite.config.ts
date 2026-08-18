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
  },
  preview: {
    allowedHosts: ["web", "localhost"],
    strictPort: true,
  },
});
