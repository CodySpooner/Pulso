import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { mockSeriesApi, noHistory, shortHistory, staleSeries } from "./trends-fixtures";

// p2-09 (UX-5) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The loaded tab, the
// keyboard tooltip on a gap day, then the loading, error, no history, short history and stale states.
// Run with `pnpm --filter web e2e:screenshots e2e/products/trends-screenshots`; output: docs/screenshots/p2-09/.
const OUT = "../../docs/screenshots/p2-09";
const URL = `/products/${PRODUCT_ID}?tab=trends`;

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 1000],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ hasTouch: width === 375 });
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await mockProductApi(page);
      });

      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(400);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage: true });
      };
      const chart = (page: Page) => page.getByTestId("trends-canvas");

      test("loaded", async ({ page }) => {
        await mockSeriesApi(page);
        await page.goto(`${URL}&range=30d`);
        await expect(chart(page)).toBeVisible();
        await shot(page, "loaded");
      });

      test("tooltip on a gap day", async ({ page }) => {
        await mockSeriesApi(page);
        await page.goto(`${URL}&range=30d`);
        await chart(page).focus();
        await page.keyboard.press("End");
        for (let i = 0; i < 8; i++) await page.keyboard.press("ArrowLeft");
        await expect(chart(page).getByText("collection gap").first()).toBeVisible();
        await shot(page, "tooltip-gap");
      });

      test("loading", async ({ page }) => {
        await mockSeriesApi(page, { hold: true });
        await page.goto(URL);
        await expect(page.getByRole("status").filter({ hasText: "Loading trends…" })).toBeAttached();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await mockSeriesApi(page, { status: 503 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "Couldn't load the trends" })).toBeVisible();
        await shot(page, "error");
      });

      test("no history", async ({ page }) => {
        await mockSeriesApi(page, { body: noHistory });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "No history for this product yet" })).toBeVisible();
        await shot(page, "no-history");
      });

      test("short history", async ({ page }) => {
        await mockSeriesApi(page, { body: shortHistory });
        await page.goto(`${URL}&range=7d`);
        await expect(chart(page)).toBeVisible();
        await shot(page, "short-history");
      });

      test("stale", async ({ page }) => {
        await mockSeriesApi(page, { body: staleSeries });
        await page.goto(`${URL}&range=30d`);
        await expect(chart(page)).toBeVisible();
        await shot(page, "stale");
      });
    });
  }
}
