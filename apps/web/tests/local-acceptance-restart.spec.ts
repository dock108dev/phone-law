import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("Slice 6A persisted state survives a complete local service restart", async ({ page }) => {
  const unexpectedHosts: string[] = [];
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (!new Set(["web", "api", "localhost", "127.0.0.1"]).has(target.hostname)) unexpectedHosts.push(target.hostname);
  });
  await page.goto("/reports/2026-08-17");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await page.getByRole("link", { name: "CL-FX-002" }).first().click();
  await expect(page.locator(".review-history")).toContainText("Incorrect");
  await expect(page.locator(".review-history")).toContainText("Missing");
  await expect(page.locator(".provenance")).toContainText("synthetic-draft-v1");

  await page.goto("/playbooks");
  await expect(page.locator("article.playbook-card").filter({ hasText: "synthetic-acceptance-v2" })).toContainText("Published");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  await page.goto("/operations");
  await expect(page.getByText(/Config v\d+/, { exact: true })).toBeVisible();
  await expect(page.getByText("Reconciliation exact", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Content-free audit history" })).toBeVisible();
  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  expect(unexpectedHosts).toEqual([]);
  await writeFile(
    `${evidenceDirectory}/restart-browser-diagnostics.json`,
    `${JSON.stringify({ persistedFeedback: true, configurationVersionPersisted: true, playbookProvenancePreserved: true, reconciliationExact: true, immutableHistoryVisible: true, accessibilityViolations: 0, externalRequests: 0 }, null, 2)}\n`,
    "utf8",
  );
});
