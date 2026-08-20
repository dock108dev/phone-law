import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";
const allowedHosts = new Set(["web", "api", "localhost", "127.0.0.1"]);

async function assertAccessible(page: Page, surface: string): Promise<void> {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(result.violations, `${surface}: ${JSON.stringify(result.violations, null, 2)}`).toEqual([]);
}

async function redactContent(page: Page): Promise<void> {
  await page.addStyleTag({
    content: ".report-item h3,.finding-card h3,.segment p,.review-history p,.call-heading p,.side-card dd { color: transparent !important; text-shadow: none !important; }",
  });
}

test("Slice 6A reviewer, administrator, and operations acceptance journey", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const unexpectedHosts: string[] = [];
  const unexpectedResponses: { route: string; status: number }[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("403 (Forbidden)")) consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (!allowedHosts.has(target.hostname)) unexpectedHosts.push(target.hostname);
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && response.status() !== 403) {
      unexpectedResponses.push({ route: new URL(response.url()).pathname, status: response.status() });
    }
  });

  // Reviewer: report reconciliation, eight sections, key examples, evidence, feedback, persistence.
  await page.goto("/reports/2026-08-17");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await expect(page.getByRole("heading", { name: "Coverage is partial." })).toBeVisible();
  const reconciliationCounts: [string, string][] = [["Expected", "11"], ["Received", "11"], ["Analyzed", "10"], ["Failed", "1"], ["Missing", "0"], ["Late", "0"]];
  for (const [label, value] of reconciliationCounts) {
    await expect(page.locator(".metric").filter({ hasText: new RegExp(`^${label}${value}$`) })).toBeVisible();
  }
  for (const section of ["Immediate attention", "Potential new matters", "Time-sensitive dates", "Dissatisfaction and escalation", "Staff commitments", "Administrative tasks", "Routine / no action", "Processing failures"]) {
    await expect(page.getByRole("heading", { name: section })).toBeVisible();
  }
  await expect(page.getByText("Synthetic demo data", { exact: true }).last()).toBeVisible();
  await assertAccessible(page, "review report");
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  await redactContent(page);
  await page.screenshot({ path: `${evidenceDirectory}/acceptance-reviewer-mobile-redacted.png`, fullPage: true });

  for (const fixture of ["CL-FX-005", "CL-FX-003", "CL-FX-006", "CL-FX-004"]) {
    await page.goto("/reports/2026-08-17");
    await page.getByRole("link", { name: fixture }).first().click();
    await expect(page.getByRole("heading", { name: fixture })).toBeVisible();
    await expect(page.getByText("Human review required.", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Original-language transcript" })).toBeVisible();
    if (fixture === "CL-FX-006") await expect(page.getByText("Uncertainty remains")).toBeVisible();
  }
  await page.goto("/reports/2026-08-17");
  await page.getByRole("link", { name: "CL-FX-002" }).first().click();
  const originalProvenance = await page.locator(".provenance").textContent();
  await page.getByRole("button", { name: /Jump to .* Staff/ }).first().click();
  await expect(page.locator(".segment.highlighted")).toBeFocused();
  await page.getByLabel("Incorrect", { exact: true }).first().check();
  await page.getByRole("button", { name: "Save feedback" }).first().click();
  await expect(page.getByText("Feedback saved as a new review event.")).toBeFocused();
  await page.getByRole("textbox", { name: /What is missing/ }).fill("Invented acceptance omission.");
  await page.getByRole("button", { name: "Add missing finding" }).click();
  await expect(page.getByText("Missing finding saved as a new review event.")).toBeFocused();
  await page.reload();
  await expect(page.locator(".review-history")).toContainText("Incorrect");
  await expect(page.locator(".review-history")).toContainText("Missing");

  await page.goto("/operations");
  await expect(page.getByRole("alert")).toContainText("Operations access denied for the reviewer role.");
  await page.goto("/playbooks");
  await expect(page.getByText("Only the demo administrator may create a draft.")).toBeVisible();
  const publishButton = page.getByRole("button", { name: "Publish synthetic draft" }).first();
  if (await publishButton.count()) {
    await publishButton.click();
    await expect(page.locator(".authorization-message")).toContainText("administrator");
  }

  // Administrator: inspect audit, create/publish a new version, configure, and preserve provenance.
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  await page.getByRole("button", { name: "Create synthetic draft" }).click();
  await expect(page.locator(".authorization-message")).toContainText("New synthetic draft created");
  const candidate = page.locator("article.playbook-card").filter({ hasText: "synthetic-acceptance-v2" });
  await expect(candidate).toContainText("Draft");
  await candidate.getByRole("button", { name: "Publish synthetic draft" }).click();
  await expect(candidate).toContainText("Published");
  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "Content-free audit history" })).toBeVisible();
  await expect(page.getByText("Average latency", { exact: true })).toBeVisible();
  await expect(page.getByText("Maximum latency", { exact: true })).toBeVisible();
  await page.getByLabel("Daily report cutoff").fill("17:45");
  await page.getByRole("button", { name: "Publish new configuration version" }).click();
  await expect(page.getByText("New immutable local configuration version published.")).toBeFocused();
  await expect(page.getByText(/Config v\d+/, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run retention evaluation" }).click();
  await expect(page.getByText("Retention evaluation and scheduled deletion run completed.")).toBeFocused();

  await page.goto("/reports/2026-08-17");
  await page.getByRole("link", { name: "CL-FX-002" }).first().click();
  expect(await page.locator(".provenance").textContent()).toBe(originalProvenance);

  // Operations: content-free triage, retry history, cancellation, recovery, no-op notification.
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-operations");
  await page.goto("/failures");
  await expect(page.getByRole("heading", { name: "Synthetic failure queue" })).toBeVisible();
  await expect(page.locator(".failure-card").filter({ hasText: "CL-FX-010" })).toContainText("Attempt 2");
  await expect(page.locator(".failure-card").filter({ hasText: "CL-FX-011" }).getByRole("button")).toBeDisabled();

  await page.goto("/uploads");
  await page.getByLabel("Generated synthetic audio").check();
  await page.getByLabel("Choose one generated audio file").setInputFiles("/synthetic-input/generated-cancel.wav");
  await page.getByLabel("Captured at").fill("2026-08-18T04:00");
  await page.getByLabel("Direction").selectOption("inbound");
  await page.getByLabel("Language hint").selectOption("en");
  await page.getByLabel("Synthetic staff extension").fill("SYN-104");
  await page.getByLabel("I attest this artifact is entirely generated or invented.").check();
  await page.getByRole("button", { name: "Submit synthetic artifact" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Ready");
  await page.getByRole("button", { name: "Cancel and delete before processing" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Cancelled");
  await expect(page.locator(".receipt-panel")).toContainText("Confirmed");

  await page.goto("/operations");
  await page.getByRole("button", { name: "Run backup / restore drill" }).click();
  await expect(page.getByText("Disposable backup and isolated restore drill passed; artifacts removed.")).toBeFocused();
  await page.getByRole("button", { name: "Preview no-op notification" }).click();
  await expect(page.getByText("Local notification preview created. Nothing was sent.")).toBeFocused();
  await expect(page.getByText("External attempts").locator("..")).toContainText("0");
  await assertAccessible(page, "operations");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: `${evidenceDirectory}/acceptance-operations-redacted.png`, fullPage: true });

  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(unexpectedHosts).toEqual([]);
  expect(unexpectedResponses).toEqual([]);
  await writeFile(
    `${evidenceDirectory}/browser-accessibility-diagnostics.json`,
    `${JSON.stringify({ accessibility: "passed", criticalViolations: 0, consoleErrors: 0, pageErrors: 0, unexpectedResponses: 0, externalRequests: 0, responsiveWidths: [1440, 1280, 390], keyboardNavigation: "passed", syntheticOnly: true }, null, 2)}\n`,
    "utf8",
  );
});
