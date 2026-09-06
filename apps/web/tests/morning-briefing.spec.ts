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
  await expect(page.getByText("Simulated morning: July 16, 2026 — reviewing July 15, 2026.", { exact: true })).toBeVisible();
  await expect(page.locator(".briefing-recap")).toHaveCount(10);
  await expect(page.locator(".briefing-attention-item")).toHaveCount(3);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await expect(page.locator(".recap-summary")).toHaveCount(10);
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(axe.violations, JSON.stringify(axe.violations)).toEqual([]);
    await page.screenshot({ path: `${evidenceDirectory}/morning-${width.toString()}.png`, fullPage: true });
  }
  // Every rendered passage must resolve to this call's original segment and return position.
  const recaps = await page.locator('.briefing-recap').evaluateAll((nodes) => nodes.map((node) => ({ id: node.id, links: Array.from(node.querySelectorAll<HTMLAnchorElement>('.briefing-evidence a')).map((link) => link.getAttribute('href') ?? '') })));
  for (const recap of recaps) {
    for (const href of recap.links) {
      await page.goto(href);
      const segmentId = href.split('#')[1];
      if (!segmentId) throw new Error('Evidence link must identify a transcript segment');
      await expect(page.locator(`[id="${segmentId}"]`)).toBeFocused();
      await expect(page.locator(`[id="${segmentId}"]`)).toHaveClass(/highlighted/);
    }
    const back = page.getByRole('link', { name: '← Back to morning briefing' });
    await back.focus();
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
  await expect(page.getByText(/Coverage is unavailable for this date/)).toBeVisible();
  await page.getByRole('link', { name: 'Latest earlier day with activity: July 15, 2026' }).click();
  await expect(page.locator('.briefing-recap')).toHaveCount(10);
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
  await writeFile(`${evidenceDirectory}/morning-browser.json`, JSON.stringify({ received: 10, attention_calls: 3, passage_links_checked: recaps.reduce((sum, recap) => sum + recap.links.length, 0), widths: [1440,390], external_requests: external.length, page_errors: errors, owner_acceptance: false }, null, 2));
});
