import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  grep: process.env.PLAYWRIGHT_GREP ? new RegExp(process.env.PLAYWRIGHT_GREP) : undefined,
  projects: [
    { name: "review-flow", testMatch: "review-flow.spec.ts" },
    {
      name: "manual-upload",
      testMatch: "manual-upload.spec.ts",
      dependencies: ["review-flow"],
    },
    {
      name: "local-operations",
      testMatch: "local-operations.spec.ts",
    },
  ],
  use: {
    baseURL: process.env.BASE_URL ?? "http://web:5173",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
});
