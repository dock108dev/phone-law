import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: process.env.BASE_URL ?? "http://web:5173",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
  },
});
