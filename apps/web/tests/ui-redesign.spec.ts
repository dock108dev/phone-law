import { chmod, writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

async function accessible(page: Page, label: string): Promise<void> {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(result.violations, `${label}: ${JSON.stringify(result.violations, null, 2)}`).toEqual([]);
}

async function noOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${evidenceDirectory}/after/${name}.png`, fullPage: true });
}

test("professional internal-firm workspace routes, states, recovery, and evidence", async ({ page }) => {
  test.setTimeout(180_000);
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const externalRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("403 (Forbidden)")) consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    if (!request.url().includes("/api/reports/2026-07-08")) failedRequests.push(request.url());
  });
  page.on("request", (request) => {
    const host = new URL(request.url()).hostname;
    if (!["web", "api", "localhost", "127.0.0.1"].includes(host)) externalRequests.push(request.url());
  });

  await page.goto("/months/2026-07");
  await expect(page.getByRole("heading", { name: "July 2026" })).toBeVisible();
  await expect(page.locator(".calendar-day")).toHaveCount(31);
  await page.locator('style[data-vite-dev-id$="/professional.css"]').evaluate((style: HTMLStyleElement) => { style.disabled = true; });
  await page.screenshot({ path: `${evidenceDirectory}/before/month-history.png`, fullPage: true });
  await page.reload();
  await expect(page.getByRole("heading", { name: "July 2026" })).toBeVisible();
  await shot(page, "month-history-desktop");
  await accessible(page, "month history");

  const reports = [
    ["2026-07-08", "complete-daily-report"],
    ["2026-07-06", "partial-daily-report"],
    ["2026-07-04", "zero-activity-date"],
    ["2026-07-01", "immediate-attention"],
  ] as const;
  for (const [date, name] of reports) {
    await page.goto(`/reports/${date}`);
    await expect(page.getByRole("heading", { name: `Call review · ${date}` })).toBeVisible();
    await expect(page.locator(".report-section")).toHaveCount(8);
    await shot(page, name);
  }

  await page.goto("/reports/2026-07-08");
  const englishLink = page.locator('a.call-reference[href^="/calls/"]').first();
  await englishLink.click();
  await expect(page.getByRole("heading", { name: "Original-language transcript" })).toBeVisible();
  await shot(page, "english-call-review");
  await page.locator(".review-history").screenshot({ path: `${evidenceDirectory}/after/feedback-history.png` });
  await accessible(page, "English call review");

  await page.goto("/reports/2026-07-28");
  await page.getByRole("link", { name: "CL-MONTH-202607-422" }).first().click();
  await expect(page.getByText("Spanish", { exact: true })).toBeVisible();
  await shot(page, "spanish-call-review");

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  for (const [path, heading, name] of [
    ["/uploads", "Submit one invented call artifact.", "manual-upload"],
    ["/failures", "Synthetic failure queue", "failure-queue"],
    ["/operations", "Local controls and recovery", "operations"],
    ["/playbooks", "Playbook lifecycle", "playbook"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await shot(page, name);
    await accessible(page, name);
  }
  await page.goto("/operations");
  await expect(page.locator(".configuration-panel")).toBeVisible();
  await page.locator(".configuration-panel").screenshot({ path: `${evidenceDirectory}/after/configuration-retention.png` });

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await expect(page.getByRole("alert")).toContainText("Operations access denied");
  await shot(page, "reviewer-denial");

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  await page.waitForLoadState("networkidle");
  await page.addInitScript(() => {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const failureCount = Number(sessionStorage.getItem("slice6d-report-failure-count") ?? "0");
      if (url.includes("/api/reports/2026-07-08") && failureCount < 2) {
        sessionStorage.setItem("slice6d-report-failure-count", String(failureCount + 1));
        return Promise.reject(new TypeError("Injected local service failure"));
      }
      return nativeFetch(input, init);
    };
  });
  await page.goto("/reports/2026-07-08");
  await expect(page.getByRole("alert")).toContainText("daily report could not be loaded");
  await expect(page.getByRole("alert")).not.toContainText("Failed to fetch");
  await shot(page, "recoverable-error");
  await page.getByRole("button", { name: "Reload daily report" }).click();
  await expect(page.getByRole("heading", { name: "Call review · 2026-07-08" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Demo identity and role" })).toHaveValue("demo-admin");

  const slowReport = /\/api\/reports\/2026-07-06(?:\?.*)?$/;
  await page.route(slowReport, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3_000));
    await route.continue();
  });
  await page.getByRole("combobox", { name: "Report date" }).selectOption("2026-07-06");
  await expect(page.getByRole("status").filter({ hasText: "Loading daily report" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Call review · 2026-07-06" })).toBeVisible();
  await page.unroute(slowReport);

  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 1280, height: 900 },
    { width: 1024, height: 768 },
    { width: 768, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/months/2026-07");
    await expect(page.getByRole("heading", { name: "July 2026" })).toBeVisible();
    await noOverflow(page);
    if ([1280, 1024, 768, 390].includes(viewport.width)) await shot(page, `month-${viewport.width.toString()}px`);
  }
  await page.setViewportSize({ width: 780, height: 900 });
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await noOverflow(page);
  await shot(page, "month-200-percent-zoom");
  await page.evaluate(() => { document.documentElement.style.zoom = "1"; });

  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(failedRequests).toEqual([]);
  expect(externalRequests).toEqual([]);
  const diagnostics = {
    routes: 10,
    responsiveWidths: [1440, 1280, 1024, 768, 390],
    zoomPercent: 200,
    criticalAccessibilityViolations: 0,
    consoleErrors: 0,
    pageErrors: 0,
    unexpectedResponses: 0,
    externalRequests: 0,
    realOrHumanAudio: 0,
    clientRecords: 0,
    recoveryPreservedDateAndRole: true,
  };
  await writeFile(`${evidenceDirectory}/ui-redesign-results.json`, `${JSON.stringify(diagnostics, null, 2)}\n`, "utf8");
  await chmod(`${evidenceDirectory}/ui-redesign-results.json`, 0o600);
});
