import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi, type FeedOptions } from "../products/fixtures";

// p2-03 (UX-2) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. Grid (with a
// provenance card open), table, loading, empty, filtered empty, degraded with gap chips, error, and the phone filter
// sheet. Run with `pnpm --filter web e2e:screenshots e2e/discover`; output: docs/screenshots/p2-03/.
const OUT = "../../docs/screenshots/p2-03";
const BLOCKED: FeedOptions["degraded"] = [{ source: "shopify_stores", source_name: "Shopify stores", state: "blocked", since: "2026-10-20T06:00:00Z" }];

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

      const shot = async (page: Page, name: string, fullPage = false) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
      };

      test("grid, card open", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(24) });
        await page.goto("/discover");
        const stores = page.getByRole("article").nth(1).getByRole("button", { name: /^Velocity, / });
        if (width === 375) await stores.tap();
        else await stores.focus();
        await expect(page.locator('[role="tooltip"]')).toContainText("Source");
        await shot(page, "grid");
      });

      test("table", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(60) });
        await page.goto("/discover?view=table");
        await expect(page.locator("tbody th a").first()).toBeVisible();
        await shot(page, "table");
      });

      test("loading", async ({ page }) => {
        await mockFeedApi(page, { hold: true });
        await page.goto("/discover");
        await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockFeedApi(page, { items: [] });
        await page.goto("/discover");
        await expect(page.getByRole("heading", { name: "No products collected yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("filtered empty", async ({ page }) => {
        await mockFeedApi(page, { items: [] });
        await page.goto("/discover?price_min=200&source=cj");
        await expect(page.getByRole("heading", { name: "No products match 2 filters" })).toBeVisible();
        await shot(page, "filtered-empty");
      });

      test("degraded and gap", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(24), degraded: BLOCKED });
        await page.goto("/discover");
        await expect(page.getByRole("main")).toContainText("Shopify stores blocked");
        await shot(page, "degraded");
      });

      test("error", async ({ page }) => {
        await mockFeedApi(page, { status: 503 });
        await page.goto("/discover");
        await expect(page.getByRole("heading", { name: "Couldn't load products" })).toBeVisible({ timeout: 15_000 });
        await shot(page, "error");
      });

      if (width === 375)
        test("filter sheet", async ({ page }) => {
          await mockFeedApi(page, { items: feedItems(24) });
          await page.goto("/discover?source=cj");
          await page.getByRole("button", { name: "Filters (1)" }).tap();
          await expect(page.getByRole("dialog", { name: "Filters" })).toBeVisible();
          await shot(page, "filter-sheet");
        });
    });
  }
}
