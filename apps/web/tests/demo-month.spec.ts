import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { DailyBriefing } from "../src/types";

import { expectMonthCountsFit } from "./month-layout";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("July month history and representative daily reports remain usable", async ({ page }) => {
  const externalRequests: string[] = [];
  const failures: string[] = [];
  page.on("request", (request) => {
    const host = new URL(request.url()).hostname;
    if (!["web", "api", "localhost", "127.0.0.1"].includes(host)) externalRequests.push(request.url());
  });
  page.on("requestfailed", (request) => failures.push(request.url()));
  test.setTimeout(180_000);
  const started = Date.now();
  await page.goto("/months/2026-07");
  await expect(page.getByRole("heading", { name: "July 2026" })).toBeVisible();
  await expect(page.locator(".calendar-day")).toHaveCount(31);
  await expect(page.locator(".calendar-day.state-zero_activity")).toHaveCount(9);
  await expect(page.getByLabel("July monthly reconciliation")).toContainText("227");
  await expect(page.getByRole("link", { name: "Previous month" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Next month" })).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: `${evidenceDirectory}/month-history.png`, fullPage: true });

  for (const width of [1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 950 });
    await expectMonthCountsFit(page);
    await page.screenshot({ path: `${evidenceDirectory}/month-counts-${width.toString()}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 780, height: 950 });
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await expectMonthCountsFit(page);
  await page.screenshot({ path: `${evidenceDirectory}/month-counts-css-zoom-200.png`, fullPage: true });
  await page.evaluate(() => { document.documentElement.style.zoom = "1"; });

  const journeys = [
    ["normal_complete", "/reports/2026-07-08", "Coverage is complete."],
    ["morning_attention", "/reports/2026-07-15", "Call review"],
    ["missing", "/reports/2026-07-23", "Coverage is partial."],
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
    if (journey === "missing") {
      await expect(page.getByLabel("Report reconciliation counts").locator(".metric").filter({ hasText: "Missing" })).toContainText("1");
    }
    if (journey === "permanent_failure") {
      await page.screenshot({ path: `${evidenceDirectory}/permanent-failure-day.png`, fullPage: true });
    }
    results.push({ journey, duration_ms: Date.now() - journeyStarted });
  }
  for (const [day, count] of [["20", 6], ["21", 14], ["03", 0], ["07", 12], ["23", 10], ["27", 12]] as const) {
    await page.goto(`/briefing/2026-07-${day}`);
    await expect(page.locator(".briefing-recap")).toHaveCount(count);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 950 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(axe.violations).toEqual([]);
      await page.screenshot({ path: `${evidenceDirectory}/day-${day}-${width.toString()}.png`, fullPage: true });
    }
  }
  let renderedRecaps = 0;
  let unavailableRecaps = 0;
  for (let day = 1; day <= 31; day++) {
    const date = `2026-07-${day.toString().padStart(2, "0")}`;
    const received = page.waitForResponse((response) => response.url().includes(`/api/briefing?business_date=${date}`) && response.ok());
    await page.goto(`/briefing/${date}`);
    const briefing = await (await received).json() as DailyBriefing;
    await expect(page.locator(".briefing-recap")).toHaveCount(briefing.calls.length);
    for (const call of briefing.calls) {
      const rendered = page.locator(`[id="call-${call.call_id}"]`);
      if (call.detail) {
        await expect(rendered.locator(".recap-summary")).toHaveText(call.detail.summary);
        for (const uncertainty of call.detail.uncertainty) await expect(rendered).toContainText(uncertainty);
        renderedRecaps++;
      } else {
        await expect(rendered).toContainText("Result unavailable for this received call.");
        await expect(rendered).toContainText("No conversation recap can be provided.");
        if (call.synthetic_reference === "CL-M2-20260707-02") {
          await expect(rendered).toContainText("No usable transcript or accepted analysis is available.");
        } else {
          expect(call.synthetic_reference).toBe("CL-M2-20260727-03");
          await expect(rendered).toContainText("A transcript was received, but no accepted analysis is available.");
        }
        unavailableRecaps++;
      }
    }
  }
  expect(renderedRecaps).toBe(224);
  expect(unavailableRecaps).toBe(2);
  const spanishStarted = Date.now();
  await page.goto("/reports/2026-07-01");
  await page.getByRole("link", { name: "CL-M2-20260701-08" }).first().click();
  await expect(page.getByText("Spanish", { exact: true })).toBeVisible();
  await expect(page.locator(".metadata").filter({ hasText: "Time" })).toContainText("7/1/2026, 3:08:00 PM EDT");
  await expect(page.getByText(/¿Puedo pedir información/).first()).toBeVisible();
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
    `${JSON.stringify({ renderedRecaps, unavailableRecaps, datesChecked: 31, accessibility: [], externalRequests: 0, failedRequests: 0, totalDurationMs: Date.now() - started, journeys: results }, null, 2)}\n`,
    "utf8",
  );
});
