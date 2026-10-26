import { expect, test, type Page } from "@playwright/test";

import { contrastMisses } from "../p2-39/screens";
import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { scoresStaleInput } from "./scores-fixtures";

// imp-589 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Trend card with a stale
// input (amber dot, last seen, Stale input chip), and the bar's link to #confidence focused by keyboard.
// Run with `pnpm --filter web e2e:screenshots e2e/products/stale-input-screenshots`; output: docs/screenshots/imp-589/.
const OUT = "../../docs/screenshots/imp-589";
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
        await mockProductApi(page, { scores: scoresStaleInput });
        await page.goto(URL);
        await expect(page.locator("#score-trend")).toContainText("Stale, last seen Sep 28: Search-interest slope");
      });

      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        // Centred, so the phone's fixed bottom bar never covers the card's foot.
        await page.locator("#score-trend").evaluate((el) => el.scrollIntoView({ block: "center" }));
        await page.waitForTimeout(300);
        await page.locator("#score-trend").screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
        // No horizontal page scroll at any width, and AA contrast in each theme.
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        expect(await page.evaluate(contrastMisses, "main")).toEqual([]);
      };

      test("stale input", async ({ page }) => {
        await shot(page, "stale-input");
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: `${OUT}/scores-${width}-${theme}.png`, fullPage: width === 375 });
      });

      test("confidence link focused", async ({ page }) => {
        await page.locator("#score-trend").getByRole("link", { name: "Stale input: how freshness counts" }).focus();
        await page.keyboard.press("Tab");
        await expect(page.locator("#score-trend").getByRole("link", { name: "Confidence: how it's computed" })).toBeFocused();
        await shot(page, "confidence-focus");
      });
    });
  }
}
