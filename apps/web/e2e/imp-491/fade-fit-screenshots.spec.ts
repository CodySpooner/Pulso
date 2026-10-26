import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi } from "../products/fixtures";

// imp-491 / imp-575 owner review screenshots, from fixtures only: Discover's table at 1440px and 375px, dark and
// light, with every source healthy and with one blocked. Run with
// `pnpm --filter web e2e:screenshots e2e/imp-491`; output: docs/screenshots/imp-491/.
const OUT = "../../docs/screenshots/imp-491";
const BLOCKED = [{ source: "shopify_stores", source_name: "Shopify stores", state: "blocked", since: "2026-10-20T06:00:00Z" }] as const;

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

      for (const [name, degraded] of [
        ["table", []],
        ["table-blocked", BLOCKED],
      ] as const)
        test(name, async ({ page }) => {
          await mockFeedApi(page, { items: feedItems(60), degraded: [...degraded] });
          await page.goto("/discover?view=table");
          await expect(page.locator("tbody th a").first()).toBeVisible();
          await shot(page, name);
        });
    });
  }
}
