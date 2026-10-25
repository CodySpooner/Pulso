import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "./fixtures";
import { empty, mockSellersApi, paused } from "./sellers-fixtures";

// p2-11 (UX-7) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The loaded tab (with
// stale and Unknown rows, and the band's no source yet card), delisted sellers included, the crawler paused, then
// loading, empty and error. Run with `pnpm --filter web e2e:screenshots e2e/products/sellers`; output:
// docs/screenshots/p2-11/. Tall viewports instead of full-page captures, which stitch the fixed top bar and bottom nav
// into the middle of the page.
const OUT = "../../docs/screenshots/p2-11";
const URL = `/products/${PRODUCT_ID}?tab=sellers`;

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 1500],
    [375, 2300],
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
        await mockSellersApi(page);
        await page.goto(URL);
        await expect(page.getByRole("region", { name: "Price spread" }).getByText("$24.00–$39.99")).toBeVisible();
        await shot(page, "loaded");
      });

      test("delisted", async ({ page }) => {
        await mockSellersApi(page);
        await page.goto(`${URL}&sellers=all`);
        if (width === 375) await page.getByText("Delisted (2)").click();
        await expect(page.getByText("Delisted Oct 18").filter({ visible: true }).first()).toBeVisible();
        await shot(page, "delisted");
      });

      test("crawler paused", async ({ page }) => {
        await mockSellersApi(page, { body: paused });
        await page.goto(URL);
        await expect(page.getByText("Store crawler stopped itself")).toBeVisible();
        await shot(page, "paused");
      });

      test("loading", async ({ page }) => {
        await mockSellersApi(page, { hold: true });
        await page.goto(URL);
        await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockSellersApi(page, { body: empty });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "No stores seen selling this yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockSellersApi(page, { status: 503 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "Couldn't load sellers" })).toBeVisible();
        await shot(page, "error");
      });
    });
  }
}
