import { expect, test, type Locator, type Page } from "@playwright/test";

// WEB-9: the /admin/ui gallery renders every section and works keyboard-only (AGENTS.md §8 checklist).

/** Presses Tab until `target` has focus; fails if it is not reachable within `max` presses. */
async function tabTo(page: Page, target: Locator, max = 80) {
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
  // The global :focus-visible ring (an outline) shows on keyboard focus.
  expect(await target.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
}

test("the UI gallery renders every section and is keyboard-navigable", async ({ page }) => {
  await page.goto("/admin/ui");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await expect(page.getByRole("heading", { level: 1, name: "UI gallery" })).toBeVisible();
  for (const name of ["Colour tokens", "Type scale", "Buttons", "Table density", "States", "Motion"]) {
    await expect(page.getByRole("heading", { level: 2, name })).toBeVisible();
  }
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Admin/UI gallery");

  await page.getByRole("link", { name: "Skip to content" }).focus();
  await page.keyboard.press("Enter");
  await tabTo(page, page.getByRole("link", { name: "Motion", exact: true }));
  await tabTo(page, page.getByRole("button", { name: "Start test" }));
  await tabTo(page, page.getByRole("region", { name: "Specimen table" }));

  const replay = page.getByRole("button", { name: "Replay motion" });
  await tabTo(page, replay);
  await page.keyboard.press("Enter");
  await expect(replay).toBeFocused();

  const month = page.getByRole("button", { name: "Month" });
  await tabTo(page, month, 10);
  await page.keyboard.press("Enter");
  await expect(month).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Week" })).toHaveAttribute("aria-pressed", "false");
});

test("the palette reaches the gallery", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await page.keyboard.press("Control+K");
  await page.getByRole("combobox").fill("gallery");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "UI gallery" })).toBeFocused();
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  for (const path of ["/", "/admin/ui", "/discover", "/not-authorized"]) {
    test(`${path} has no horizontal page scroll at 375px`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    });
  }
});
