import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

test("local operations administrator, operations, reviewer denial, responsiveness, and accessibility", async ({ page }) => {
  const consoleErrors: string[] = [];
  const unexpectedRequests: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("403 (Forbidden)")) {
      consoleErrors.push(message.text());
    }
  });
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (!new Set(["web", "api", "localhost", "127.0.0.1"]).has(target.hostname)) {
      unexpectedRequests.push(target.hostname);
    }
  });

  const navigation = await page.goto("/operations");
  expect(navigation).not.toBeNull();
  const headers = navigation!.headers();
  expect(headers["cache-control"]).toBe("no-store");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["cross-origin-resource-policy"]).toBe("same-origin");
  expect(headers["permissions-policy"]).toBe("camera=(), microphone=(), geolocation=()");
  expect(headers["referrer-policy"]).toBe("no-referrer");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-robots-tag"]).toBe("noindex, nofollow, noarchive");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  await expect(page.getByRole("heading", { name: "Local controls and recovery" })).toBeVisible();
  await expect(page.getByText("Local / synthetic", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Local development", { exact: true })).toBeVisible();
  await expect(page.getByText("Zero external requests", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Operational reconciliation" })).toBeVisible();
  await expect(page.getByText("Reconciliation exact", { exact: true })).toBeVisible();

  const accessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);

  await page.setViewportSize({ width: 1440, height: 1000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/operations-administrator-redacted.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/operations-mobile-redacted.png`, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.getByLabel("Daily report cutoff").fill("17:45");
  await page.getByRole("button", { name: "Publish new configuration version" }).click();
  await expect(page.getByText("New immutable local configuration version published.")).toBeFocused();
  await expect(page.getByText("Config v2", { exact: true })).toBeVisible();
  await expect(page.locator(".configuration-history")).toContainText("Version 2");

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-operations");
  await expect(page.getByText("Only the demo administrator may publish configuration.")).toBeVisible();
  await page.getByRole("button", { name: "Run backup / restore drill" }).focus();
  await expect(page.getByRole("button", { name: "Run backup / restore drill" })).toBeFocused();
  await page.getByRole("button", { name: "Run backup / restore drill" }).click();
  await expect(page.getByText("Disposable backup and isolated restore drill passed; artifacts removed.")).toBeFocused();
  await page.getByRole("button", { name: "Preview no-op notification" }).click();
  await expect(page.getByText("Local notification preview created. Nothing was sent.")).toBeFocused();

  const bodyText = (await page.locator("body").innerText()).toLowerCase();
  for (const forbidden of ["phone number", "credential", "raw request", "provider output", "absolute path", "filename"]) {
    expect(bodyText).not.toContain(forbidden);
  }
  expect(bodyText).not.toMatch(/\+1[ .-]?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}/);

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await expect(page.getByRole("alert")).toContainText("Operations access denied for the reviewer role.");
  await page.screenshot({ path: `${evidenceDirectory}/operations-reviewer-denial-redacted.png`, fullPage: true });
  const denialAccessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(denialAccessibility.violations, JSON.stringify(denialAccessibility.violations, null, 2)).toEqual([]);

  expect(consoleErrors).toEqual([]);
  expect(unexpectedRequests).toEqual([]);
  await writeFile(
    `${evidenceDirectory}/browser-diagnostics.json`,
    `${JSON.stringify({ consoleErrors, unexpectedRequests, accessibility: { administrator: [], reviewerDenial: [] }, keyboardNavigation: "passed", responsiveWidths: [1440, 390], contentInspection: "passed" }, null, 2)}\n`,
    "utf8",
  );
});
