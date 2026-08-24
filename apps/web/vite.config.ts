import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const configuredApiUrl = process.env.VITE_API_BASE_URL?.trim();
let localApiConnectSource = "";
if (configuredApiUrl) {
  const parsed = new URL(configuredApiUrl);
  if (
    parsed.protocol === "http:" &&
    new Set(["api", "localhost", "127.0.0.1"]).has(parsed.hostname) &&
    parsed.username === "" &&
    parsed.password === "" &&
    parsed.pathname === "/" &&
    parsed.search === "" &&
    parsed.hash === ""
  ) {
    localApiConnectSource = ` ${parsed.origin}`;
  }
}

const securityHeaders = {
  "Cache-Control": "no-store",
  "Content-Security-Policy": `default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:${localApiConnectSource}`,
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-Robots-Tag": "noindex, nofollow, noarchive",
};

export default defineConfig({
  plugins: [react()],
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    allowedHosts: ["web", "localhost"],
    headers: securityHeaders,
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
    headers: securityHeaders,
    strictPort: true,
  },
});
