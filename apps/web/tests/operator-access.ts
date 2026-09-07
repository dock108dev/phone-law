import { expect, type Page } from "@playwright/test";

export async function selectDemoRole(page: Page, role: string): Promise<void> {
  const returnUrl = page.url();
  if (!await page.getByRole("combobox", { name: "Demo identity and role" }).isVisible()) {
    await page.getByRole("link", { name: "Operator access", exact: true }).click();
  }
  await page.getByRole("combobox", { name: "Demo identity and role" }).selectOption(role);
  if (page.url() !== returnUrl) await page.goto(returnUrl);
}

export async function expectDemoRole(page: Page, role: string): Promise<void> {
  const returnUrl = page.url();
  if (!await page.getByRole("combobox", { name: "Demo identity and role" }).isVisible()) {
    await page.getByRole("link", { name: "Operator access", exact: true }).click();
  }
  await expect(page.getByRole("combobox", { name: "Demo identity and role" })).toHaveValue(role);
  if (page.url() !== returnUrl) await page.goto(returnUrl);
}
