import { defineConfig, type Project } from "@playwright/test";

const acceptanceProjects: Project[] = process.env.INCLUDE_LOCAL_ACCEPTANCE === "1" ? [
  { name: "local-acceptance", testMatch: "local-acceptance.spec.ts" },
  { name: "local-acceptance-restart", testMatch: "local-acceptance-restart.spec.ts" },
] : [];
const demoMonthProjects: Project[] = process.env.INCLUDE_DEMO_MONTH === "1" ? [
  { name: "demo-month", testMatch: "demo-month.spec.ts" },
] : [];

export default defineConfig({
  testDir: "./tests",
  outputDir: "/tmp/colacci-law-playwright-results",
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
    ...acceptanceProjects,
    ...demoMonthProjects,
  ],
  use: {
    baseURL: process.env.BASE_URL ?? "http://web:5173",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
});
