import type { DailyBriefing } from "../src/types";
import { writeFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("ten-call morning, dates, original evidence and keyboard return", async ({ page }) => {
  test.setTimeout(120_000);
  const external: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => { if (!["web", "api", "localhost", "127.0.0.1"].includes(new URL(request.url()).hostname)) external.push(request.url()); });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Calls from July 15, 2026" })).toBeVisible();
  await expect(page.getByText("Simulated morning: July 16, 2026 · New York time", { exact: true })).toBeVisible();
  await expect(page.locator(".briefing-recap")).toHaveCount(10);
  await expect(page.locator(".briefing-attention-item")).toHaveCount(3);
  for (const width of [1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await expect(page.locator(".recap-summary")).toHaveCount(10);
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(axe.violations, JSON.stringify(axe.violations)).toEqual([]);
    await page.screenshot({ path: `${evidenceDirectory}/morning-${width.toString()}.png`, fullPage: true });
  }
  // Open every call, verify every original segment, and return by keyboard.
  const recaps = await page.locator('.briefing-recap').evaluateAll((nodes) => nodes.map((node) => ({ id: node.id, href: node.querySelector('a.open-call')?.getAttribute('href') ?? '' })));
  let passages = 0;
  for (const recap of recaps) {
    expect(recap.href).not.toBe('');
    await page.locator(`#${recap.id}`).getByRole('link').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.segment').first()).toBeVisible();
    const ids = await page.locator('.segment').evaluateAll((nodes) => nodes.map((node) => node.id));
    expect(ids.length).toBeGreaterThan(0);
    for (const segmentId of ids) {
      await page.goto(`${recap.href}#${segmentId}`);
      await expect(page.locator(`[id="${segmentId}"]`)).toBeFocused();
      await expect(page.locator(`[id="${segmentId}"]`)).toHaveClass(/highlighted/);
      passages++;
    }
    await page.getByRole('link', { name: '← Back to morning briefing' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator(`#${recap.id}`)).toBeFocused();
  }
  await page.locator('.briefing-recap').nth(2).getByRole('link').first().click();
  await expect(page.getByText('Buenos días, soy Lucía Soto. ¿Puedo entregar una copia en vez del documento original?', { exact: true })).toBeVisible();
  await page.screenshot({ path: `${evidenceDirectory}/morning-spanish-evidence.png`, fullPage: true });
  await page.getByRole('link', { name: '← Back to morning briefing' }).click();
  await page.getByLabel('Review another date').fill('2026-07-19');
  await page.getByRole('button', { name: 'Open day' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Calls from July 19, 2026' })).toBeVisible();
  if (process.env.MONTH_V2 === '1') {
    await expect(page.getByText(/No calls expected or received/)).toBeVisible();
    await page.getByRole('link', { name: 'Latest earlier day with activity: July 17, 2026' }).click();
    await expect(page.locator('.briefing-recap')).toHaveCount(13);
    await page.goto('/briefing/2026-08-01');
    await expect(page.getByText(/Coverage is unavailable for this date/)).toBeVisible();
  } else {
    await expect(page.getByText(/Coverage is unavailable for this date/)).toBeVisible();
    await page.getByRole('link', { name: 'Latest earlier day with activity: July 15, 2026' }).click();
    await expect(page.locator('.briefing-recap')).toHaveCount(10);
  }
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
  await writeFile(`${evidenceDirectory}/morning-browser.json`, JSON.stringify({ received: 10, attention_calls: 3, passage_links_checked: passages, widths: [1440,1280,1024,768,390], external_requests: external.length, page_errors: errors, owner_acceptance: false }, null, 2));
});

test("restrained shell, supported meaning, operator permissions and long recaps", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".briefing-recap")).toHaveCount(10);
  await expect(page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link")).toHaveCount(2);
  await expect(page.getByRole("combobox", { name: "Demo identity and role" })).toHaveCount(0);
  await expect(page.getByText(/Dataset:|Name stated in conversation|saved assessments/)).toHaveCount(0);
  await expect(page.locator(".briefing-evidence a,[title]")).toHaveCount(0);
  await expect(page.getByText("A lawyer callback about the letter.", { exact: false })).toHaveCount(1);
  await expect(page.getByText("Staff promised:", { exact: false })).toHaveCount(1);
  await expect(page.getByText("The call does not confirm that the replacement was sent.", { exact: false })).toBeVisible();
  await expect(page.getByText("Consider reviewing:", { exact: false })).toHaveCount(1);
  await expect(page.locator(".language-note")).toHaveText(["Spanish · English recap", "Spanish · English recap"]);
  await page.getByRole("link", { name: "Operator access", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Demo identity and role" })).toHaveValue("demo-reviewer");
  await page.getByRole("link", { name: "Operations", exact: true }).click();
  await expect(page.getByText("Operations access denied for the reviewer role.")).toBeVisible();
  const denied = await page.request.get("/api/operations/overview", { headers: { "X-Demo-Principal": "demo-reviewer" } });
  expect(denied.status()).toBe(403);
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-operations");
  await expect(page.getByText("Operations access denied for the reviewer role.")).toHaveCount(0);
  const allowed = await page.request.get("/api/operations/overview", { headers: { "X-Demo-Principal": "demo-operations" } });
  expect(allowed.status()).toBe(200);
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await page.getByRole("link", { name: "Morning briefing", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Demo identity and role" })).toHaveCount(0);
  await page.route("**/api/briefing*", async (route) => {
    const response = await route.fetch();
    const data = await response.json() as DailyBriefing;
    const detail = data.calls[0]?.detail;
    if (!detail) throw new Error("Long-content probe requires a real synthetic recap");
    detail.summary = `${"Invented long-content layout probe. ".repeat(40)}${"LongUnbrokenSyntheticText".repeat(12)}`;
    await route.fulfill({ response, json: data });
  });
  await page.reload();
  await expect(page.locator(".recap-summary").first()).toContainText("LongUnbrokenSyntheticText");
  await page.setViewportSize({ width: 390, height: 950 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/long-recap-mobile.png`, fullPage: true });
  await page.unroute("**/api/briefing*");
  await page.reload();
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/briefing-200-percent.png`, fullPage: true });
});
