import { expect, test, type Page } from "@playwright/test";

import { mockPopularApi } from "./fixtures";

// p2-33 (P2-29 b) owner review screenshots, from synthetic fixtures only: 1440px and 375px, dark and light. The list,
// major brands shown, loading, empty, error, stale and no source yet. Run with
// `pnpm --filter web e2e:screenshots e2e/google-popular`; output: docs/screenshots/p2-33/.
const OUT = "../../docs/screenshots/p2-33";
const rows = (page: Page) => page.getByRole("region", { name: "Google popular products" }).locator("tbody tr");

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
        // No horizontal page scroll at any width: the table scrolls inside its own region.
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("list", async ({ page }) => {
        await mockPopularApi(page);
        await page.goto("/google-popular");
        await expect(rows(page)).toHaveCount(30);
        await shot(page, "list");
      });

      test("major brands shown", async ({ page }) => {
        await mockPopularApi(page);
        await page.goto("/google-popular?brands=all");
        await expect(rows(page)).toHaveCount(40);
        await shot(page, "major-brands");
      });

      test("loading", async ({ page }) => {
        await mockPopularApi(page, { hold: true });
        await page.goto("/google-popular");
        await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockPopularApi(page, { empty: true });
        await page.goto("/google-popular");
        await expect(page.getByRole("heading", { name: "No Google popular report yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockPopularApi(page, { status: 503 });
        await page.goto("/google-popular");
        await expect(page.getByRole("heading", { name: "Couldn't load Google popular products" })).toBeVisible({ timeout: 15_000 });
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        await mockPopularApi(page, { stale: true });
        await page.goto("/google-popular");
        await expect(page.getByText("The newest report is for the week of Oct 5, 2026")).toBeVisible();
        await shot(page, "stale");
      });

      test("no source yet", async ({ page }) => {
        await mockPopularApi(page, { noPrevious: true });
        await page.goto("/google-popular");
        await expect(page.getByText("Weekly change: no source yet.")).toBeVisible();
        await shot(page, "no-source");
      });
    });
  }
}
