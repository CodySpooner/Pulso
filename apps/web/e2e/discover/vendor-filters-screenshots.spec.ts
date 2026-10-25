import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi } from "../products/fixtures";
import { mockSearchApi, openPalette } from "../search/fixtures";

// imp-242 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The palette's store row
// (Enter now shows its products), Discover filtered by a store (where that row lands), both chips with a long supplier
// name, loading, empty, an unknown id, error and stale. Run with `pnpm --filter web e2e:screenshots
// e2e/discover/vendor-filters`; output: docs/screenshots/imp-242/.
const OUT = "../../docs/screenshots/imp-242";
const chips = (page: Page) => page.getByRole("list", { name: "Store and supplier filters" });

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
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("palette store row", async ({ page }) => {
        await mockSearchApi(page);
        const input = await openPalette(page);
        await input.fill("glowbeam");
        await expect(page.getByRole("option", { name: /glowbeam\.example\.test/ })).toHaveAttribute("aria-selected", "true");
        await shot(page, "palette");
      });

      test("store chip", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(6) });
        await page.goto("/discover?store=4101");
        await expect(chips(page)).toContainText("glowbeam.example.test");
        await expect(page.getByRole("article").first()).toBeVisible();
        await shot(page, "store");
      });

      test("both chips, long name", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(6) });
        await page.goto("/discover?store=4101&supplier=90");
        await expect(chips(page)).toContainText("Yiwu Brightstar");
        await shot(page, "chips");
      });

      test("loading", async ({ page }) => {
        await mockFeedApi(page, { hold: true });
        await page.goto("/discover?store=4101");
        await expect(chips(page).locator("div[aria-hidden]")).toBeVisible();
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockFeedApi(page, { items: [] });
        await page.goto("/discover?store=4102");
        await expect(page.getByRole("heading", { name: "No products match this filter" })).toBeVisible();
        await shot(page, "empty");
      });

      test("unknown id", async ({ page }) => {
        await mockFeedApi(page, { items: [] });
        await page.goto("/discover?supplier=404");
        await expect(chips(page)).toContainText("#404, not found");
        await shot(page, "unknown");
      });

      test("error", async ({ page }) => {
        await mockFeedApi(page, { status: 503 });
        await page.goto("/discover?store=4101");
        await expect(page.getByRole("heading", { name: "Couldn't load products" })).toBeVisible({ timeout: 15_000 });
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(6), degraded: [{ source: "shopify_stores", source_name: "Shopify stores", state: "stale", since: "2026-10-20T06:00:00Z" }] });
        await page.goto("/discover?store=4101");
        await expect(page.getByRole("main")).toContainText("Shopify stores stale");
        await shot(page, "stale");
      });
    });
  }
}
