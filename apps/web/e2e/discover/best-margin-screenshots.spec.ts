import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi } from "../products/fixtures";

// p2-27 (UX-8 part c) owner review screenshots, from fixtures only: Discover's best margin at 1440px and 375px, dark
// and light. The grid with a margin's provenance card open, and the table's Best margin column. Run with
// `pnpm --filter web e2e:screenshots e2e/discover/best-margin`; output: docs/screenshots/p2-27/.
const OUT = "../../docs/screenshots/p2-27";

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

      test("grid, margin card open", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(24) });
        await page.goto("/discover");
        const margin = page.getByRole("article").nth(0).getByRole("button", { name: /^Best landed margin/ });
        if (width === 375) await margin.tap();
        else await margin.focus();
        await expect(page.locator('[role="tooltip"]:not([data-state="closed"])')).toContainText("Landed cost");
        await shot(page, "grid");
      });

      test("table", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(60) });
        await page.goto("/discover?view=table");
        await expect(page.locator("tbody th a").first()).toBeVisible();
        await shot(page, "table");
      });
    });
  }
}
