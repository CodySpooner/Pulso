import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "./fixtures";
import { incomplete, mockProfitApi, noPrice, noSupplier, stale } from "./profit-fixtures";

// p2-20 (UX-8 part b) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The complete
// worked example, then incomplete (no freight quote, duty not set), no market price, no supplier (no source yet),
// stale inputs, loading and error. Run with `pnpm --filter web e2e:screenshots e2e/products/profit`; output:
// docs/screenshots/p2-20/. Tall viewports instead of full-page captures, which stitch the fixed top bar and bottom nav
// into the middle of the page.
const OUT = "../../docs/screenshots/p2-20";
const URL = `/products/${PRODUCT_ID}?tab=profit`;

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 1300],
    [375, 2700],
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
        await mockProfitApi(page);
        await page.goto(URL);
        await expect(page.getByRole("tabpanel").getByText("+$0.03")).toBeVisible();
        await shot(page, "loaded");
      });

      test("incomplete", async ({ page }) => {
        await mockProfitApi(page, { body: incomplete });
        await page.goto(URL);
        await expect(page.getByRole("region", { name: "Profit and margin are withheld" })).toBeVisible();
        await shot(page, "incomplete");
      });

      test("no market price", async ({ page }) => {
        await mockProfitApi(page, { body: noPrice });
        await page.goto(URL);
        await expect(page.getByText("No market price yet: enter one")).toBeVisible();
        await shot(page, "no-price");
      });

      test("no supplier", async ({ page }) => {
        await mockProfitApi(page, { body: noSupplier });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "No supplier cost yet" })).toBeVisible();
        await shot(page, "no-supplier");
      });

      test("stale", async ({ page }) => {
        await mockProfitApi(page, { body: stale });
        await page.goto(URL);
        await expect(page.getByText("Some inputs are older than expected.")).toBeVisible();
        await shot(page, "stale");
      });

      test("loading", async ({ page }) => {
        await mockProfitApi(page, { hold: true });
        await page.goto(URL);
        await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await mockProfitApi(page, { status: 503 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "Couldn't calculate profit" })).toBeVisible();
        await shot(page, "error");
      });
    });
  }
}
