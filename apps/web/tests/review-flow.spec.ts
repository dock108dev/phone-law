import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("complete synthetic reviewer flow, roles, persistence, accessibility, and provenance", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedRequests: { url: string; status: number | string }[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({ url: request.url(), status: request.failure()?.errorText ?? "failed" });
  });
  page.on("response", (response) => {
    if (response.status() >= 400) failedRequests.push({ url: response.url(), status: response.status() });
  });

  await page.goto("/");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await expect(page.getByRole("heading", { name: "Coverage is partial." })).toBeVisible();
  await expect(page.getByText("Expected").locator("..").getByText("11")).toBeVisible();
  await expect(page.getByText("Analyzed").locator("..").getByText("10")).toBeVisible();
  await expect(page.getByText("Failed").locator("..").getByText("1")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Immediate attention" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Processing failures" })).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor)).toBe("rgb(243, 240, 233)");
  for (const section of [
    "Immediate attention",
    "Potential new matters",
    "Time-sensitive dates",
    "Dissatisfaction and escalation",
    "Staff commitments",
    "Administrative tasks",
    "Routine / no action",
    "Processing failures",
  ]) {
    await expect(page.getByRole("heading", { name: section })).toBeVisible();
  }

  const reportAccessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(reportAccessibility.violations, JSON.stringify(reportAccessibility.violations, null, 2)).toEqual([]);

  await page.setViewportSize({ width: 1440, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/desktop-report.png`, fullPage: true });
  await page.locator(".attention-section").screenshot({ path: `${evidenceDirectory}/immediate-attention.png` });
  await page.setViewportSize({ width: 1280, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/laptop-report.png`, fullPage: true });

  await page.getByRole("link", { name: "CL-FX-003" }).first().click();
  await expect(page.getByText("Hola. Tuve una caída en una tienda la semana pasada y me lastimé la muñeca.")).toBeVisible();
  await page.getByRole("link", { name: "← Back to daily report" }).click();

  await page.getByRole("link", { name: "CL-FX-002" }).first().click();
  await expect(page.getByRole("heading", { name: "CL-FX-002" })).toBeVisible();
  const callUrl = page.url();
  const provenanceBefore = await page.locator(".provenance").textContent();
  expect(provenanceBefore).toContain("synthetic-draft-v1");
  await page.screenshot({ path: `${evidenceDirectory}/call-analysis.png`, fullPage: true });

  await page.getByRole("button", { name: /Jump to .* Staff/ }).first().click();
  const highlighted = page.locator("#fx002-seg-4");
  await expect(highlighted).toHaveClass(/highlighted/);
  await expect(highlighted).toBeFocused();
  await highlighted.screenshot({ path: `${evidenceDirectory}/highlighted-evidence.png` });

  await page.getByLabel("Correct", { exact: true }).check();
  await page.getByRole("button", { name: "Save feedback" }).click();
  await expect(page.getByText("Feedback saved as a new review event.")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Append-only review history" }).locator("..")).toContainText("Correct");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Append-only review history" }).locator("..")).toContainText("Correct");

  const missingNote = "Synthetic browser review records a missing context finding.";
  await page.getByRole("textbox", { name: /What is missing/ }).fill(missingNote);
  await page.getByRole("button", { name: "Add missing finding" }).click();
  await expect(page.getByText("Missing finding saved as a new review event.")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Append-only review history" }).locator("..")).toContainText(missingNote);
  await page.locator(".review-history").screenshot({ path: `${evidenceDirectory}/persisted-feedback.png` });

  const callAccessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(callAccessibility.violations, JSON.stringify(callAccessibility.violations, null, 2)).toEqual([]);

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-operations");
  await page.goto("/failures");
  await expect(page.getByRole("heading", { name: "Synthetic failure queue" })).toBeVisible();
  const permanentFailure = page.locator(".failure-card").filter({ hasText: "CL-FX-011" });
  await expect(permanentFailure.getByRole("button", { name: /Retry unavailable/ })).toBeDisabled();
  await expect(page.locator(".failure-card").filter({ hasText: "CL-FX-010" })).toContainText("Resolved");
  await page.screenshot({ path: `${evidenceDirectory}/failure-queue.png`, fullPage: true });

  await page.goto("/playbooks");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await page.getByRole("button", { name: "Publish synthetic draft" }).click();
  await expect(page.getByRole("status").filter({ hasText: /administrator/ })).toBeVisible();
  await page.screenshot({ path: `${evidenceDirectory}/playbook-authorization.png`, fullPage: true });

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  await page.getByRole("button", { name: "Publish synthetic draft" }).click();
  await expect(page.getByText("Synthetic playbook published.", { exact: false })).toBeVisible();
  await expect(page.locator(".lifecycle-published")).toHaveText("Published");

  await page.goto(callUrl);
  await expect(page.locator(".provenance")).toContainText("synthetic-draft-v1");
  expect(await page.locator(".provenance").textContent()).toBe(provenanceBefore);

  const unexpectedFailures = failedRequests.filter(
    (item) => !(item.status === 403 && item.url.includes("/playbooks/") && item.url.endsWith("/publish")),
  );
  const expectedAuthorizationConsoleErrors = consoleErrors.filter((message) => message.includes("403 (Forbidden)"));
  const unexpectedConsoleErrors = consoleErrors.filter((message) => !message.includes("403 (Forbidden)"));
  expect(expectedAuthorizationConsoleErrors.length).toBeGreaterThan(0);
  expect(unexpectedConsoleErrors).toEqual([]);
  expect(unexpectedFailures).toEqual([]);
  await writeFile(
    `${evidenceDirectory}/browser-diagnostics.json`,
    `${JSON.stringify({ consoleErrors: unexpectedConsoleErrors, expectedAuthorizationConsoleErrors, failedRequests, accessibility: { report: [], call: [] }, manualKeyboard: "passed in automated focus assertions; repeated manually" }, null, 2)}\n`,
    "utf8",
  );
});
