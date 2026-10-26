import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi, mockProductApi, PRODUCT_ID, type ProductMock } from "./fixtures";
import { scoresNone, scoresStale, scoresUnscored } from "./scores-fixtures";

// imp-460 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Overview's score cards
// loaded (a reason's source open), NULL rows with the margin floor, no source yet, loading, error and stale; and
// Discover's Trend cell in the table and on a card.
// Run with `pnpm --filter web e2e:screenshots e2e/products/scores-screenshots`; output: docs/screenshots/imp-460/.
const OUT = "../../docs/screenshots/imp-460";
const URL = `/products/${PRODUCT_ID}`;
const STATES: [string, ProductMock][] = [
  ["unscored", { scores: scoresUnscored }],
  ["no-source", { scores: scoresNone }],
  ["loading", { holdScores: true }],
  ["error", { scoresStatus: 503 }],
  ["stale", { scores: scoresStale }],
];

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

      const shot = async (page: Page, name: string, fullPage = true) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
        // No horizontal page scroll at any width.
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      };

      test("loaded, a reason's source open", async ({ page }) => {
        await mockProductApi(page);
        await page.goto(URL);
        const reason = page.locator("#score-trend").getByRole("button", { name: "Velocity growth (Shopify inventory)" });
        if (width === 375) await reason.tap();
        else await reason.focus();
        await expect(page.locator('[role="tooltip"]')).toContainText("Source: Shopify stores");
        await shot(page, "loaded");
      });

      for (const [name, mock] of STATES)
        test(name, async ({ page }) => {
          await mockProductApi(page, mock);
          await page.goto(URL);
          await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
          if (name !== "loading") await expect(page.getByRole("region", { name: "Where it appears" })).toBeVisible();
          await shot(page, name, width === 375);
        });

      test("discover trend", async ({ page }) => {
        await mockFeedApi(page, { items: feedItems(20) });
        await page.goto(width === 375 ? "/discover" : "/discover?view=table");
        await expect(page.getByRole("link", { name: /^Trend Score: / }).first()).toBeVisible();
        await shot(page, "discover", false);
      });
    });
  }
}
