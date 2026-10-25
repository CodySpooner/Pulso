import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "./fixtures";
import { mockSuppliersApi, noPrice, stale, suppliers } from "./suppliers-fixtures";

// p2-26 (UX-6) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The loaded tab (picks,
// an out-of-stock row, the unquoted cheap row), no market price (no source yet), stale, loading, empty, error, and the
// Profit tab a supplier opens in. Run with `pnpm --filter web e2e:screenshots e2e/products/suppliers`; output:
// docs/screenshots/p2-26/. Tall viewports instead of full-page captures, which stitch the fixed top bar and bottom nav
// into the middle of the page.
const OUT = "../../docs/screenshots/p2-26";
const URL = `/products/${PRODUCT_ID}?tab=suppliers`;

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 1300],
    [375, 2600],
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

      test("loaded", async ({ page }) => {
        await mockSuppliersApi(page);
        await page.goto(URL);
        await expect(page.getByRole("region", { name: "Best margin", exact: true })).toContainText("CJ Dropshipping");
        await shot(page, "loaded");
      });

      test("no market price", async ({ page }) => {
        await mockSuppliersApi(page, { body: noPrice });
        await page.goto(URL);
        await expect(page.getByText("Margins are withheld for every supplier.")).toBeVisible();
        await shot(page, "no-price");
      });

      test("stale", async ({ page }) => {
        await mockSuppliersApi(page, { body: stale });
        await page.goto(URL);
        await expect(page.getByText("Some supplier numbers are older than expected.")).toBeVisible();
        await shot(page, "stale");
      });

      test("loading", async ({ page }) => {
        await mockSuppliersApi(page, { hold: true });
        await page.goto(URL);
        await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockSuppliersApi(page, { body: { ...suppliers, rows: [], picks: { best_margin: null, fastest: null }, as_of: null } });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "No supplier matched yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockSuppliersApi(page, { status: 503 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "Couldn't load suppliers" })).toBeVisible();
        await shot(page, "error");
      });

      test("profit with the chosen supplier", async ({ page }) => {
        await mockSuppliersApi(page);
        await page.goto(`/products/${PRODUCT_ID}?tab=profit&supplier=88140`);
        await expect(page.getByText("listing you opened from Suppliers")).toBeVisible();
        await shot(page, "profit-chosen");
      });
    });
  }
}
