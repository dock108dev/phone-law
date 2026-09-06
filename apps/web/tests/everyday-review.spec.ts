import { writeFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("everyday assessments, uncertain saves, return context and coverage", async ({ page }) => {
  test.setTimeout(120_000);
  const external: string[] = [];
  page.on("request", (request) => {
    if (!["web", "api", "localhost", "127.0.0.1"].includes(new URL(request.url()).hostname)) external.push(request.url());
  });
  await page.goto("/");
  await expect(page.getByText("Dataset: demo-month-2026-07-v2")).toBeVisible();
  const recap = page.locator(".briefing-recap").nth(3);
  const recapId = await recap.getAttribute("id");
  await recap.getByRole("link", { name: "Inspect call and assess findings" }).click();
  const callUrl = page.url();
  const finding = page.locator(".finding-card").first();
  const before = await page.locator(".review-history li").count();
  for (const [label, note] of [["Correct", "Engineering confirmation"], ["Incorrect", "Engineering rejection"], ["Partially Correct", "Engineering revised assessment"]]) {
    if (!label || !note) throw new Error("Assessment case is incomplete");
    await finding.getByRole("radio", { name: label, exact: true }).check();
    await finding.getByRole("textbox").fill(note);
    await finding.getByRole("button", { name: "Save feedback" }).dblclick();
    await expect(finding.getByText("Feedback saved as a new review event.")).toBeFocused();
    await expect(page.locator(".review-history li").last()).toContainText(note);
  }
  await expect(page.locator(".review-history li")).toHaveCount(before + 3);
  // Drop the response after the server has committed. Retrying the persisted intent
  // must return that same event even after a browser reload, not append a duplicate.
  let dropped = false;
  await page.route("**/api/analyses/*/reviews", async (route) => {
    if (!dropped && route.request().method() === "POST") {
      dropped = true;
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      await route.abort("failed");
    } else await route.continue();
  });
  await finding.getByRole("radio", { name: "Unsupported", exact: true }).check();
  await finding.getByRole("textbox").fill("Engineering response-loss probe");
  await finding.getByRole("button", { name: "Save feedback" }).click();
  await expect(finding.getByText(/Save not confirmed/)).toBeVisible();
  await expect(finding.getByRole("textbox")).toHaveValue("Engineering response-loss probe");
  await page.reload();
  await expect(finding.getByRole("textbox")).toHaveValue("Engineering response-loss probe");
  await finding.getByRole("button", { name: "Retry same assessment" }).click();
  await expect(finding.getByText("Feedback saved as a new review event.")).toBeVisible();
  await expect(page.locator(".review-history li")).toHaveCount(before + 4);
  await page.unroute("**/api/analyses/*/reviews");
  // Definite denial preserves entered information without claiming success.
  await page.route("**/api/analyses/*/reviews", (route) => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: { error: "Engineering denied-save probe" } }) }));
  await finding.getByRole("radio", { name: "Correct", exact: true }).check();
  await finding.getByRole("textbox").fill("Engineering unsaved draft");
  await finding.getByRole("button", { name: "Save feedback" }).click();
  await expect(finding.getByText(/Assessment was not saved/)).toBeVisible();
  await expect(finding.getByRole("textbox")).toHaveValue("Engineering unsaved draft");
  await expect(page.locator(".review-history li")).toHaveCount(before + 4);
  await page.unroute("**/api/analyses/*/reviews");
  await page.screenshot({ path: `${evidenceDirectory}/review-error-draft.png`, fullPage: true });
  await page.getByRole("link", { name: "← Back to morning briefing" }).click();
  await expect(page.locator(`[id="${recapId ?? ""}"]`)).toBeFocused();
  await page.goBack();
  await expect(page).toHaveURL(callUrl);
  await page.goForward();
  await expect(page.locator(`[id="${recapId ?? ""}"]`)).toBeFocused();
  await page.locator(".briefing-attention-item").first().getByRole("link", { name: "Supporting passage" }).click();
  await expect(page.locator(".segment.highlighted")).toBeFocused();
  await page.goBack();
  await expect(page.locator(`[id="${recapId ?? ""}"]`)).toBeFocused();
  await page.getByRole("link", { name: "Browse month history" }).click();
  await page.getByRole("link", { name: /^2026-07-03,/ }).click();
  await expect(page.getByRole("heading", { name: "Calls from July 3, 2026" })).toBeVisible();
  await expect(page.getByText(/No eligible synthetic calls were expected/)).toBeVisible();
  for (const [date, text] of [["2026-07-06", "Late arrival"], ["2026-07-07", "Some received calls have no usable result"], ["2026-07-23", "Expected input has not arrived"], ["2026-07-27", "Some received calls have no usable result"], ["2026-08-01", "Coverage is unavailable"]]) {
    if (!date || !text) throw new Error("Coverage case is incomplete");
    await page.getByLabel("Review another date").fill(date);
    await page.getByRole("button", { name: "Open day" }).click();
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible();
  }
  await page.getByRole("link", { name: "Manual upload", exact: true }).click();
  await expect(page.getByText("Upload access denied for the reviewer role.")).toBeVisible();
  await page.getByRole("link", { name: "Morning briefing", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Calls from August 1, 2026" })).toBeVisible();
  await page.goto(callUrl);
  await expect(page.locator(".review-history li")).toHaveCount(before + 4);
  let refreshFailed = false;
  await page.route("**/api/calls/*", async (route) => {
    if (!refreshFailed) {
      refreshFailed = true;
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { error: "Engineering history-refresh fault" } }) });
    } else await route.continue();
  });
  await finding.getByRole("radio", { name: "Correct", exact: true }).check();
  await finding.getByRole("textbox").fill("Engineering saved despite refresh failure");
  await finding.getByRole("button", { name: "Save feedback" }).click();
  await expect(finding.getByText(/Assessment saved .*History could not refresh/)).toBeVisible();
  await page.reload();
  await expect(page.locator(".review-history li")).toHaveCount(before + 5);
  await expect(page.locator(".review-history li").last()).toContainText("Engineering saved despite refresh failure");
  await page.unroute("**/api/calls/*");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: /^Jump to/ }).first().focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".segment.highlighted")).toBeFocused();
  for (const width of [1440, 1280, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(axe.violations, JSON.stringify(axe.violations)).toEqual([]);
    await writeFile(`${evidenceDirectory}/review-axe-${width.toString()}.json`, JSON.stringify(axe));
    await page.screenshot({ path: `${evidenceDirectory}/review-${width.toString()}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1280, height: 950 });
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(await page.locator(".detail-panel,.segment,.finding-card,.review-history").evaluateAll((nodes) => nodes.every((node) => {
    const rect = node.getBoundingClientRect();
    return rect.left >= 0 && rect.right <= window.innerWidth + 1;
  }))).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/review-200-percent.png`, fullPage: true });
  expect(external).toEqual([]);
  await writeFile(`${evidenceDirectory}/everyday-review.json`, JSON.stringify({ confirmation: true, rejection: true, revised_assessment: true, response_loss_idempotency: true, draft_preserved: true, reload_persistence: true, browser_back_forward: true, coverage: true, widths: [1440,1280,1024,768,390], zoom: 200, external_requests: external, owner_verdict_recorded: false }, null, 2));
});


test("briefing loading and recoverable error remain readable", async ({ page }) => {
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/briefing*", async (route) => { await held; await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { error: "Engineering temporary coverage failure" } }) }); });
  await page.goto("/");
  await expect(page.getByText("Loading morning briefing")).toBeVisible();
  await page.screenshot({ path: `${evidenceDirectory}/briefing-loading.png`, fullPage: true });
  release?.();
  await expect(page.getByRole("alert")).toContainText("Engineering temporary coverage failure");
  await page.screenshot({ path: `${evidenceDirectory}/briefing-error.png`, fullPage: true });
  await page.unroute("**/api/briefing*");
  await page.getByRole("button", { name: "Reload morning briefing" }).click();
  await expect(page.locator(".briefing-recap")).toHaveCount(10);
});
