import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("July month history and representative daily reports remain usable", async ({ page }) => {
  const externalRequests: string[] = [];
  const failures: string[] = [];
  page.on("request", (request) => {
    const host = new URL(request.url()).hostname;
    if (!["web", "api", "localhost", "127.0.0.1"].includes(host)) externalRequests.push(request.url());
  });
  page.on("requestfailed", (request) => failures.push(request.url()));
  const started = Date.now();
  await page.goto("/months/2026-07");
  await expect(page.getByRole("heading", { name: "July 2026" })).toBeVisible();
  await expect(page.locator(".calendar-day")).toHaveCount(31);
  await expect(page.locator(".calendar-day.state-zero_activity")).toHaveCount(8);
  await expect(page.getByLabel("July monthly reconciliation")).toContainText("500");
  await expect(page.getByRole("link", { name: "Previous month" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Next month" })).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: `${evidenceDirectory}/month-history.png`, fullPage: true });

  const journeys = [
    ["normal_complete", "/reports/2026-07-08", "Coverage is complete."],
    ["high_attention", "/reports/2026-07-01", "Immediate attention"],
    ["partial_late", "/reports/2026-07-06", "Late recordings: 1"],
    ["zero_activity", "/reports/2026-07-04", "Coverage is zero activity."],
    ["duplicates", "/reports/2026-07-02", "Duplicate deliveries excluded"],
    ["permanent_failure", "/reports/2026-07-07", "Processing failures"],
  ] as const;
  const results: { journey: string; duration_ms: number }[] = [];
  for (const [journey, path, visibleText] of journeys) {
    const journeyStarted = Date.now();
    await page.goto(path);
    await expect(page.getByText(visibleText, { exact: false }).first()).toBeVisible();
    await expect(page.locator(".report-section")).toHaveCount(8);
    if (journey === "permanent_failure") {
      await page.screenshot({ path: `${evidenceDirectory}/permanent-failure-day.png`, fullPage: true });
    }
    results.push({ journey, duration_ms: Date.now() - journeyStarted });
  }
  const spanishStarted = Date.now();
  await page.goto("/reports/2026-07-28");
  await page.getByRole("link", { name: "CL-MONTH-202607-422" }).first().click();
  await expect(page.getByText("Spanish", { exact: true })).toBeVisible();
  await expect(page.getByText(/Solicito|Llamo|Por favor|Estoy inconforme/).first()).toBeVisible();
  await page.screenshot({ path: `${evidenceDirectory}/spanish-call.png`, fullPage: true });
  results.push({ journey: "spanish_heavy", duration_ms: Date.now() - spanishStarted });
  await page.goto("/reports/2026-07-08?month=2026-07");
  await page.getByRole("link", { name: /Back to July 2026 month history/ }).click();
  await expect(page.getByRole("heading", { name: "July 2026" })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/month-history-mobile.png`, fullPage: true });
  expect(externalRequests).toEqual([]);
  expect(failures).toEqual([]);
  await writeFile(
    `${evidenceDirectory}/browser-results.json`,
    `${JSON.stringify({ accessibility: [], externalRequests: 0, failedRequests: 0, totalDurationMs: Date.now() - started, journeys: results }, null, 2)}\n`,
    "utf8",
  );
});
