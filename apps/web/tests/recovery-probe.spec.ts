import { writeFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("technical successful and failed retries preserve attempts and missing input", async ({ page }) => {
  await page.goto("/briefing/2026-08-17");
  await expect(page.locator(".briefing-recap")).toHaveCount(2);
  await expect(page.getByText(/0 analyzed · 2 received with failed analysis · 1 expected but missing/)).toBeVisible();
  await page.getByRole("link", { name: "Failures", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("administrators and operations");
  await page.getByText("Demo controls", { exact: true }).click();
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-operations");
  const success = page.locator(".failure-card").filter({ hasText: "CL-FX-010" });
  await page.route("**/api/failures/*/retry", (route) => route.abort("failed"));
  await success.getByRole("button", { name: "Retry synthetic processing" }).click();
  await expect(success).toContainText("Retry outcome could not be confirmed");
  await expect(success).toContainText("Attempt 1");
  await page.unroute("**/api/failures/*/retry");
  await page.reload();
  await success.getByRole("button", { name: "Retry synthetic processing" }).click();
  await expect(success).toContainText("Resolved");
  await expect(success).toContainText("Attempt 2");
  const failed = page.locator(".failure-card").filter({ hasText: "CL-FX-011" });
  await expect(failed.getByRole("button", { name: /Retry unavailable/ })).toBeDisabled();
  await expect(failed).toContainText("Attempt 1");
  await page.reload();
  await expect(success).toContainText("Resolved");
  await expect(failed).toContainText("Current failure");
  await page.screenshot({ path: `${evidenceDirectory}/technical-recovery.png`, fullPage: true });
  await page.getByRole("link", { name: "Morning briefing", exact: true }).click();
  await expect(page.locator(".briefing-recap")).toHaveCount(2);
  await expect(page.getByText(/1 analyzed · 1 received with failed analysis · 1 expected but missing/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/1 analyzed · 1 received with failed analysis · 1 expected but missing/)).toBeVisible();
  await writeFile(`${evidenceDirectory}/technical-recovery.json`, JSON.stringify({ received: 2, analyzed: 1, failed: 1, missing: 1, attempts_preserved: true, reload: true, owner_feedback: false }));
});
