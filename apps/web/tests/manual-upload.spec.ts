import { writeFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const evidenceDirectory = process.env.EVIDENCE_DIR ?? "/evidence";

async function chooseAudio(page: Page, path: string): Promise<void> {
  await page.getByLabel("Choose one generated audio file").setInputFiles(path);
}

async function fillAudioMetadata(page: Page): Promise<void> {
  await page.getByLabel("Direction").selectOption("inbound");
  await page.getByLabel("Captured at").fill("2026-08-18T04:00");
  await page.getByLabel("Language hint").selectOption("en");
  await page.getByLabel("Synthetic staff extension").fill("SYN-104");
  await page.getByLabel("I attest this artifact is entirely generated or invented.").check();
}

test("manual upload local synthetic audio and transcript bridge", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedResponses: { route: string; status: number }[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => { pageErrors.push(error.message); });
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push({ route: new URL(response.url()).pathname, status: response.status() });
    }
  });

  await page.goto("/uploads");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-reviewer");
  await expect(page.getByRole("alert")).toContainText("Upload access denied");
  const reviewerStatus = await page.evaluate(async () => {
    const form = new FormData();
    form.set("file", new Blob(["invented"], { type: "audio/wav" }), "generated.wav");
    return (await fetch("http://api:8000/api/uploads/audio", {
      method: "POST",
      headers: { "X-Demo-Principal": "demo-reviewer" },
      body: form,
    })).status;
  });
  expect(reviewerStatus).toBe(403);
  await page.screenshot({ path: `${evidenceDirectory}/upload-authorization-denial.png`, fullPage: true });

  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-admin");
  await expect(page.getByText("Upload access denied for the reviewer role.")).not.toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel("Choose one generated audio file")).toBeEnabled();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: `${evidenceDirectory}/synthetic-upload-form-desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 800 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: `${evidenceDirectory}/synthetic-upload-form-laptop.png`, fullPage: true });
  const uploadAccessibility = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(uploadAccessibility.violations, JSON.stringify(uploadAccessibility.violations, null, 2)).toEqual([]);

  await chooseAudio(page, "/synthetic-input/generated-success.wav");
  await fillAudioMetadata(page);
  expect(await page.locator("form.upload-form").evaluate((element) => (element as HTMLFormElement).checkValidity())).toBe(true);
  await page.getByRole("button", { name: "Submit synthetic artifact" }).click();
  await expect(page.locator(".upload-message")).toHaveText("Internal receipt created. Input validation passed.");
  await expect(page.getByText("No file selected. The filename is never retained.")).toBeVisible();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Ready");
  await page.locator(".receipt-panel").screenshot({ path: `${evidenceDirectory}/successful-upload-receipt.png` });
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Analyzed", { timeout: 15_000 });
  await expect(page.getByText("Synthetic processing completed.")).toBeFocused();
  const callLink = page.getByRole("link", { name: "Open completed call" });
  const callPath = await callLink.getAttribute("href");
  expect(callPath).toMatch(/^\/calls\/[a-f0-9]{32}$/);

  await page.getByRole("link", { name: "Open resulting report" }).click();
  await expect(page.getByRole("heading", { name: /Coverage is/ })).toBeVisible();
  await page.addStyleTag({ content: ".report-item h3 { color: transparent !important; }" });
  await page.screenshot({ path: `${evidenceDirectory}/uploaded-report-item.png`, fullPage: true });

  if (!callPath) throw new Error("completed call link missing");
  await page.goto(callPath);
  await expect(page.locator(".call-heading h1")).toBeVisible();
  await page.getByRole("button", { name: /Jump to .* Staff/ }).first().click();
  await expect(page.locator(".segment.highlighted")).toBeFocused();
  await page.addStyleTag({
    content: ".call-heading p,.finding-card h3,.segment p,.side-card dd,.review-history p { color: transparent !important; }",
  });
  await page.screenshot({ path: `${evidenceDirectory}/uploaded-call-evidence.png`, fullPage: true });
  await page.getByLabel("Correct", { exact: true }).first().check();
  await page.getByRole("button", { name: "Save feedback" }).first().click();
  await expect(page.getByText("Feedback saved as a new review event.")).toBeFocused();
  await page.reload();
  await expect(page.locator(".review-history")).toContainText("Correct");

  await page.goto("/uploads");
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption("demo-operations");
  await page.getByLabel("Invented transcript JSON").check();
  await page.getByLabel("Choose one invented transcript JSON file").setInputFiles("/synthetic-input/invented-transcript.json");
  await page.getByLabel("Captured at").fill("2026-08-17T14:00");
  await page.getByLabel("Direction").selectOption("inbound");
  await page.getByLabel("Language hint").selectOption("en");
  await page.getByLabel("Synthetic staff extension").fill("SYN-104");
  await page.getByLabel("I attest this artifact is entirely generated or invented.").check();
  await page.getByRole("button", { name: "Submit synthetic artifact" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Analyzed");
  await page.reload();
  await expect(page.getByRole("combobox", { name: "Demo identity and role" })).toHaveValue("demo-operations");
  await page.getByLabel("Invented transcript JSON").check();
  await page.getByLabel("Choose one invented transcript JSON file").setInputFiles("/synthetic-input/invented-transcript.json");
  await page.getByLabel("Captured at").fill("2026-08-17T14:00");
  await page.getByLabel("I attest this artifact is entirely generated or invented.").check();
  await page.getByRole("button", { name: "Submit synthetic artifact" }).click();
  await expect(page.getByText("Duplicate recognized.", { exact: false })).toBeFocused();

  await page.getByLabel("Generated synthetic audio").check();
  await chooseAudio(page, "/synthetic-input/generated-retry.wav");
  await fillAudioMetadata(page);
  await page.getByRole("button", { name: "Submit synthetic artifact" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Transcription Failed", { timeout: 15_000 });
  await page.locator(".receipt-panel").screenshot({ path: `${evidenceDirectory}/retryable-upload-failure.png` });
  await page.getByRole("button", { name: "Retry same call" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Analyzed", { timeout: 15_000 });
  await expect(page.locator(".receipt-panel")).toContainText("Attempt 2");

  await chooseAudio(page, "/synthetic-input/generated-cancel.wav");
  await fillAudioMetadata(page);
  await page.getByRole("button", { name: "Submit synthetic artifact" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Ready");
  await page.getByRole("button", { name: "Cancel and delete before processing" }).click();
  await expect(page.locator(".receipt-panel .upload-state")).toHaveText("Cancelled");
  await expect(page.locator(".receipt-panel")).toContainText("Confirmed");
  await page.locator(".receipt-panel").screenshot({ path: `${evidenceDirectory}/cancelled-upload.png` });

  await page.keyboard.press("Shift+Tab");
  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
  const unexpectedResponses = failedResponses.filter(
    (item) => !(item.status === 403 && item.route === "/api/uploads/audio"),
  );
  const unexpectedConsoleErrors = consoleErrors.filter(
    (message) => !message.includes("403 (Forbidden)"),
  );
  expect(unexpectedResponses).toEqual([]);
  expect(unexpectedConsoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  await writeFile(
    `${evidenceDirectory}/manual-upload-browser-diagnostics.json`,
    `${JSON.stringify({ expectedAuthorizationDenials: 1, unexpectedResponseCount: 0, unexpectedConsoleErrorCount: 0, pageErrorCount: 0, accessibilityViolationCount: uploadAccessibility.violations.length, desktopWidth: 1440, laptopWidth: 1280, horizontalOverflow: false, keyboardFocus: "confirmed" }, null, 2)}\n`,
    "utf8",
  );
});
