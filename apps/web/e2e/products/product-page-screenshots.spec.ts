import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID, stale, unmatched } from "./fixtures";

// p2-02 (UX-3) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The loaded header
// with a provenance card open, then the loading, no source yet, stale, not found and error states.
// Run with `pnpm --filter web e2e:screenshots e2e/products`; output: docs/screenshots/p2-02/.
const OUT = "../../docs/screenshots/p2-02";
const URL = `/products/${PRODUCT_ID}`;

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
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage: width < 1024 });
      };

      test("loaded, card open", async ({ page }) => {
        await mockProductApi(page);
        await page.goto(URL);
        const low = page.getByRole("button", { name: /^Lowest retail price/ });
        if (width === 375) await low.tap();
        else await low.focus();
        await expect(page.locator('[role="tooltip"]')).toContainText("Raw payload");
        await shot(page, "loaded");
      });

      test("loading", async ({ page }) => {
        await mockProductApi(page, { hold: true });
        await page.goto(URL);
        await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("no source yet", async ({ page }) => {
        await mockProductApi(page, { body: unmatched });
        await page.goto(`${URL}?tab=suppliers`);
        await expect(page.getByText("No supplier listing matched yet.")).toBeVisible();
        await shot(page, "no-source");
      });

      test("stale", async ({ page }) => {
        await mockProductApi(page, { body: stale });
        await page.goto(URL);
        await expect(page.getByText("Some numbers are older than expected.")).toBeVisible();
        await shot(page, "stale");
      });

      test("not found", async ({ page }) => {
        await mockProductApi(page, { status: 404 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "No product has this ID" })).toBeVisible();
        await shot(page, "not-found");
      });

      test("error", async ({ page }) => {
        await mockProductApi(page, { status: 503 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "Couldn't load this product" })).toBeVisible();
        await shot(page, "error");
      });
    });
  }
}
