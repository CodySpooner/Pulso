import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi } from "../products/fixtures";
import { mockExport, OVER_CAP } from "./export-fixtures";

// p4-09 (WF-7a) owner review screenshots, from fixtures only: Discover's Export CSV at 1440px and 375px, dark and
// light, in each state. Run with `pnpm --filter web e2e:screenshots e2e/discover/export-csv`; output:
// docs/screenshots/p4-09/.
const OUT = "../../docs/screenshots/p4-09";
const exportButton = (page: Page) => page.getByRole("button", { name: /^(Export CSV|Preparing)/ });

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
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width); // no page scroll
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("table with Export CSV", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(60), pageSize: 24 });
        await mockExport(page);
        await page.goto("/discover?view=table");
        await expect(page.locator("tbody th a").first()).toBeVisible();
        await exportButton(page).focus(); // its focus ring
        await shot(page, "table");
      });

      test("preparing", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(24) });
        await mockExport(page, ["hold"]);
        await page.goto("/discover?view=table");
        await exportButton(page).click();
        await expect(exportButton(page)).toHaveText(width === 375 ? "Preparing…" : "Preparing export…", { useInnerText: true });
        await shot(page, "preparing");
      });

      test("over the cap", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(24) });
        await mockExport(page, ["over-cap"]);
        await page.goto("/discover?view=table");
        await exportButton(page).click();
        await expect(page.getByRole("main").getByRole("alert")).toHaveText(OVER_CAP);
        await shot(page, "over-cap");
      });

      test("transport error with Retry", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(24) });
        await mockExport(page, ["down"]);
        await page.goto("/discover?view=table");
        await exportButton(page).click();
        await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
        await shot(page, "error");
      });

      test("nothing to export", async ({ page }) => {
        await mockFeedApi(page, { items: [] });
        await page.goto("/discover?price_min=900");
        await expect(page.getByRole("heading", { name: "No products match this filter" })).toBeVisible();
        await exportButton(page).focus();
        await expect(page.getByRole("tooltip")).toHaveText("Nothing to export");
        await shot(page, "empty");
      });
    });
  }
}
