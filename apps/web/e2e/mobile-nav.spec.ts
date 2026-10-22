import { expect, test, type Page } from "@playwright/test";

// Review P0-08b #1: dismissing the navigation sheet returns focus to the button that opened it; following a
// link to another page focuses that page's h1 instead.
async function openSheet(page: Page, opener: string) {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
  const button = page.getByRole("button", { name: opener, exact: true });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  return button;
}

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("Esc closes the sheet and focus returns to More", async ({ page }) => {
    const more = await openSheet(page, "More");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(more).toBeFocused();
  });
});

test.describe("tablet", () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test("Close menu returns focus to the menu button", async ({ page }) => {
    const menu = await openSheet(page, "Open menu");
    await page.getByRole("button", { name: "Close menu" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(menu).toBeFocused();
  });

  test("a link to another page focuses its heading", async ({ page }) => {
    await openSheet(page, "Open menu");
    await page.getByRole("dialog").getByRole("link", { name: /^Discover/ }).click();
    await expect(page).toHaveURL(/\/discover$/);
    await expect(page.getByRole("heading", { level: 1, name: "Discover" })).toBeFocused();
  });
});
