import type { CallDetail } from "../src/types";
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
  await expect(page.getByRole("heading", { name: "Calls from July 15, 2026" })).toBeVisible();
  const recap = page.locator(".briefing-recap").nth(3);
  const recapId = await recap.getAttribute("id");
  await recap.getByRole("link", { name: /Open call/ }).click();
  const callUrl = page.url();
  const finding = page.locator(".finding-card").first();
  await finding.locator("summary").click();
  const before = await page.locator(".review-history li").count();
  for (const [label, note] of [["Correct", "Engineering confirmation"], ["Incorrect", "Engineering rejection"], ["Partially Correct", "Engineering revised assessment"]]) {
    if (!label || !note) throw new Error("Assessment case is incomplete");
    await finding.getByRole("radio", { name: label, exact: true }).check();
    await finding.getByRole("textbox").fill(note);
    await finding.getByRole("button", { name: "Save assessment" }).dblclick();
    await expect(finding.getByText("Assessment saved.")).toBeFocused();
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
  await finding.getByRole("button", { name: "Save assessment" }).click();
  await expect(finding.getByText(/Save not confirmed/)).toBeVisible();
  await expect(finding.getByRole("textbox")).toHaveValue("Engineering response-loss probe");
  await page.reload();
  await expect(finding.getByRole("textbox")).toHaveValue("Engineering response-loss probe");
  await finding.getByRole("button", { name: "Retry same assessment" }).click();
  await expect(finding.getByText("Assessment saved.")).toBeVisible();
  await expect(page.locator(".review-history li")).toHaveCount(before + 4);
  await page.unroute("**/api/analyses/*/reviews");
  // Definite denial preserves entered information without claiming success.
  await page.route("**/api/analyses/*/reviews", (route) => route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: { error: "Engineering denied-save probe" } }) }));
  await finding.getByRole("radio", { name: "Correct", exact: true }).check();
  await finding.getByRole("textbox").fill("Engineering unsaved draft");
  await finding.getByRole("button", { name: "Save assessment" }).click();
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
  await page.locator(".briefing-recap").nth(3).getByRole("link", { name: /Open call/ }).click();
  await page.getByRole("button", { name: /^Jump to/ }).first().click();
  await expect(page.locator(".segment.highlighted")).toBeFocused();
  await page.goBack();
  await expect(page.locator(`[id="${recapId ?? ""}"]`)).toBeFocused();
  await page.getByRole("link", { name: "Month history" }).click();
  await page.getByRole("link", { name: /^2026-07-03,/ }).click();
  await expect(page.getByRole("heading", { name: "Calls from July 3, 2026" })).toBeVisible();
  await expect(page.getByText(/No calls expected or received/)).toBeVisible();
  for (const [date, text] of [["2026-07-06", "late arrival"], ["2026-07-07", "no usable analysis"], ["2026-07-23", "missing. No recap"], ["2026-07-27", "no usable analysis"], ["2026-08-01", "Coverage is unavailable"]]) {
    if (!date || !text) throw new Error("Coverage case is incomplete");
    await page.getByLabel("Review another date").fill(date);
    await page.getByRole("button", { name: "Open day" }).click();
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible();
  }
  await page.getByRole("link", { name: "Operator access", exact: true }).click();
  await page.getByRole("link", { name: "Manual upload", exact: true }).click();
  await expect(page.getByText("Upload access denied for the reviewer role.")).toBeVisible();
  await page.getByRole("link", { name: "Morning briefing", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Calls from August 1, 2026" })).toBeVisible();
  await page.goto(callUrl);
  await expect(page.locator(".review-history li")).toHaveCount(before + 4);
  await finding.locator("summary").click();
  let refreshFailed = false;
  await page.route("**/api/calls/*", async (route) => {
    if (!refreshFailed) {
      refreshFailed = true;
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { error: "Engineering history-refresh fault" } }) });
    } else await route.continue();
  });
  await finding.getByRole("radio", { name: "Correct", exact: true }).check();
  await finding.getByRole("textbox").fill("Engineering saved despite refresh failure");
  await finding.getByRole("button", { name: "Save assessment" }).click();
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

test("call disclosures preserve unavailable evidence, long text and missing-assessment retries", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/");
  await page.locator(".briefing-recap").nth(2).getByRole("link").click();
  const url = page.url();
  await expect(page.locator(".translation-note")).toContainText("English paraphrases");
  const evidence = page.getByRole("button", { name: /^Jump to/ }).first();
  await evidence.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".segment.highlighted")).toBeFocused();
  await expect(page.locator(".segment.highlighted")).toContainText("Buenos días, soy Lucía Soto");
  await page.getByRole("button", { name: "Return to statement" }).click();
  await expect(evidence).toBeFocused();
  await page.goto(`${url}#unavailable-passage`);
  await expect(page.getByText("This supporting passage is unavailable.", { exact: false })).toBeVisible();
  await page.route("**/api/calls/*", async (route) => {
    const response = await route.fetch();
    const data = await response.json() as CallDetail;
    data.identity_label = "NombreSintéticoLargo".repeat(20);
    const firstSegment = data.transcript_segments[0];
    if (!firstSegment) throw new Error("Long-content probe requires a segment");
    firstSegment.text = "Pasaje sintético largo con contexto. ".repeat(100) + "PalabraLarga".repeat(50);
    await route.fulfill({ response, json: data });
  });
  await page.goto(`${url}#am03-s1`);
  await page.reload();
  await expect(page.locator(".segment.highlighted")).toContainText("Pasaje sintético largo");
  await page.setViewportSize({ width: 390, height: 950 });
  await page.locator(".analysis-side summary").first().click();
  await page.locator(".provenance summary").click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/long-spanish-details-mobile.png`, fullPage: true });
  await page.unroute("**/api/calls/*");
  await page.goto(url);
  const before = await page.locator(".review-history li").count();
  await page.locator(".missing-disclosure summary").click();
  await page.getByLabel(/What is missing/).fill("Engineering missing-assessment response loss");
  await page.route("**/api/analyses/*/reviews", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    await route.abort("failed");
  });
  await page.getByRole("button", { name: "Add missing finding" }).click();
  await expect(page.getByText(/Save not confirmed/)).toBeVisible();
  await page.unroute("**/api/analyses/*/reviews");
  await page.reload();
  await expect(page.getByLabel(/What is missing/)).toHaveValue("Engineering missing-assessment response loss");
  await page.getByRole("button", { name: "Retry same assessment" }).click();
  await expect(page.getByText("Missing finding saved.", { exact: true })).toBeFocused();
  await expect(page.locator(".review-history li")).toHaveCount(before + 1);
  await page.route("**/api/calls/*", async (route) => {
    const response = await route.fetch();
    const data = await response.json() as CallDetail; data.transcript_segments = [];
    await route.fulfill({ response, json: data });
  });
  await page.reload();
  await page.locator(".transcript-disclosure summary").click();
  await expect(page.getByText("Transcript unavailable.", { exact: false })).toBeVisible();
  await page.unroute("**/api/calls/*");
  await page.route("**/api/calls/*", (route) => route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:{error:"Call temporarily unavailable"}})}));
  await page.reload();
  await expect(page.getByRole("alert")).toContainText("Call temporarily unavailable");
  await page.unroute("**/api/calls/*");
  await page.getByRole("button", { name: "Reload call review" }).click();
  await expect(page.locator(".call-heading")).toBeVisible();
});

test("direct call links retain their day through history and report date changes", async ({ page, context }) => {
  await page.goto("/");
  const href = await page.locator(".briefing-recap").nth(4).getByRole("link").getAttribute("href");
  if (!href) throw new Error("A direct call link is required");
  const direct = await context.newPage();
  await direct.goto(href);
  const returnHref = await direct.getByRole("link", { name: "← Back to morning briefing" }).getAttribute("href");
  await expect(direct.getByRole("link", { name: "Morning briefing", exact: true })).toHaveAttribute("href", returnHref ?? "");
  await direct.getByRole("link", { name: "Month history" }).click();
  await expect(direct.locator('.calendar-day[aria-current="date"]')).toHaveAttribute("href", "/briefing/2026-07-15");
  await direct.getByRole("link", { name: "← Return to selected briefing" }).click();
  await expect(direct.locator('.briefing-recap:focus')).toContainText("Priya Lane");
  await direct.getByRole("link", { name: "Coverage details" }).click();
  await direct.getByLabel("Report date").selectOption("2026-07-08");
  await expect(direct).toHaveURL(/\/reports\/2026-07-08$/);
  await direct.reload();
  await expect(direct.getByRole("heading", { name: "Call review · 2026-07-08" })).toBeVisible();
  await direct.close();
});
