import { expect, test, type Page } from "@playwright/test";

import { mockAmazonApi } from "./fixtures";

// p3-04 (AMZ-1b) owner review screenshots, from synthetic fixtures only: 1440px and 375px, dark and light. The lists,
// one filtered list, loading, empty, error, stale and no source yet. Run with
// `pnpm --filter web e2e:screenshots e2e/amazon`; output: docs/screenshots/p3-04/.
const OUT = "../../docs/screenshots/p3-04";
const heads = (page: Page) => page.getByRole("region", { name: "Amazon ranks" }).locator("th[scope=colgroup]");

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

      test("lists", async ({ page }) => {
        await mockAmazonApi(page);
        await page.goto("/amazon");
        await expect(heads(page)).toHaveCount(3);
        await shot(page, "lists");
      });

      test("one list", async ({ page }) => {
        await mockAmazonApi(page);
        await page.goto("/amazon?category=Home+%26+Kitchen&kind=movers");
        await expect(heads(page)).toHaveCount(1);
        await shot(page, "filtered");
      });

      test("loading", async ({ page }) => {
        await mockAmazonApi(page, { hold: true });
        await page.goto("/amazon");
        await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockAmazonApi(page, { empty: true });
        await page.goto("/amazon");
        await expect(page.getByRole("heading", { name: "No Amazon import yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockAmazonApi(page, { status: 503 });
        await page.goto("/amazon");
        await expect(page.getByRole("heading", { name: "Couldn't load Amazon ranks" })).toBeVisible({ timeout: 15_000 });
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        await mockAmazonApi(page, { stale: true });
        await page.goto("/amazon");
        await expect(page.getByText("The newest Amazon ranks here are from Oct 5, 2026")).toBeVisible();
        await shot(page, "stale");
      });

      test("no source yet", async ({ page }) => {
        await mockAmazonApi(page, { noSource: true });
        await page.goto("/amazon");
        await expect(page.getByRole("heading", { name: "Amazon: no source yet" })).toBeVisible();
        await shot(page, "no-source");
      });
    });
  }
}
