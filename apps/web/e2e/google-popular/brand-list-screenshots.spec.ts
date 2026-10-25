import { expect, test, type Page } from "@playwright/test";

import { brandRule, mockPopularApi } from "./fixtures";

// p2-37 (DEC-277) owner review screenshots, from synthetic fixtures only: 1440px and 375px, dark and light. A row's
// Hide brand, the undo toast, every chip with hidden brands shown, everything hidden, and a failed change. Run with
// `pnpm --filter web e2e:screenshots e2e/google-popular/brand-list`; output: docs/screenshots/p2-37/.
const OUT = "../../docs/screenshots/p2-37";
const table = (page: Page) => page.getByRole("region", { name: "Google popular products" });
const rows = (page: Page) => table(page).locator("tbody tr");

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ hasTouch: width === 375 });
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      });

      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("hide action", async ({ page }) => {
        await mockPopularApi(page);
        await page.goto("/google-popular");
        await expect(rows(page)).toHaveCount(30);
        await table(page).getByRole("button", { name: "Hide brand Kestrelle" }).first().focus(); // as keyboard focus shows it
        await shot(page, "hide-action");
      });

      test("hidden with undo", async ({ page }) => {
        await mockPopularApi(page);
        await page.goto("/google-popular");
        await table(page).getByRole("button", { name: "Hide brand Kestrelle" }).first().click();
        await expect(rows(page)).toHaveCount(25);
        await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
        await shot(page, "hidden-undo");
      });

      test("hidden brands shown", async ({ page }) => {
        await mockPopularApi(page, { rules: new Map([["ordwell", brandRule("Ordwell", "hide")]]) });
        await page.goto("/google-popular?brands=all");
        await expect(rows(page)).toHaveCount(40); // Vantoro: Major; Ordwell: Hidden
        await shot(page, "chips");
      });

      test("everything hidden", async ({ page }) => {
        const rules = new Map([
          ["kestrelle", brandRule("Kestrelle", "hide")],
          ["ordwell", brandRule("Ordwell", "hide")],
        ]);
        await mockPopularApi(page, { rules, rows: 2 });
        await page.goto("/google-popular");
        await expect(page.getByRole("heading", { name: "All 2 products are hidden" })).toBeVisible();
        await shot(page, "all-hidden");
      });

      test("failed change", async ({ page }) => {
        await mockPopularApi(page, { writeStatus: 503 });
        await page.goto("/google-popular");
        await table(page).getByRole("button", { name: "Hide brand Kestrelle" }).first().click();
        await expect(page.getByText("Couldn't change Kestrelle")).toBeVisible();
        await shot(page, "failed-change");
      });
    });
  }
}
