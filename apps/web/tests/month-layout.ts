import { expect, type Page } from "@playwright/test";

/** Check the actual labels and numeric text, including internal clipping. */
export async function expectMonthCountsFit(page: Page): Promise<void> {
  await expect(page.locator(".calendar-day")).toHaveCount(31);
  await expect.poll(async () => page.locator(".calendar").evaluate((calendar) => {
    const failures: string[] = [];
    const calendarBounds = calendar.getBoundingClientRect();
    for (const day of calendar.querySelectorAll(".calendar-day")) {
      const name = day.getAttribute("aria-label") ?? "unknown day";
      if (day.classList.contains("state-zero_activity")) continue;
      const bounds = day.getBoundingClientRect();
      const values = day.querySelectorAll("dd");
      if (values.length !== 5) failures.push(`${name}: expected five count values`);
      for (const value of values) {
        if (!/^\d+$/.test(value.textContent.trim())) failures.push(`${name}: missing numeric value`);
      }
      for (const item of day.querySelectorAll("dt, dd")) {
        const range = document.createRange();
        range.selectNodeContents(item);
        const text = range.getBoundingClientRect();
        const itemBounds = item.getBoundingClientRect();
        const left = Math.max(0, calendarBounds.left, bounds.left, itemBounds.left);
        const right = Math.min(window.innerWidth, calendarBounds.right, bounds.right, itemBounds.right);
        if (text.width <= 0 || text.height <= 0 || text.left < left - 1 || text.right > right + 1
          || text.top < bounds.top - 1 || text.bottom > bounds.bottom + 1) {
          failures.push(`${name}: offscreen or clipped ${item.textContent.trim()}`);
        }
      }
    }
    return failures;
  }), { message: "Every month-day label and count must fit its visible card without horizontal scrolling" }).toEqual([]);
}
