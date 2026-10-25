import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { decided, mockKeywordsApi, trackingOff, type KeywordsMock } from "./keywords-fixtures";

// imp-358 (+ imp-355, imp-343) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The
// Search keywords section with tracking off (no tracked legend) and on (the legend), and the first relevance number's
// tooltip opened from the keyboard: on phones it carries what the one-line helper leaves out.
// Run with `pnpm --filter web e2e:screenshots e2e/products/keywords-relevance`; output: docs/screenshots/imp-358/.
const OUT = "../../docs/screenshots/imp-358";
const URL = `/products/${PRODUCT_ID}?tab=trends`;
const section = (page: Page) => page.getByRole("region", { name: "Search keywords" });

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

      const open = async (page: Page, options: KeywordsMock) => {
        await mockKeywordsApi(page, options);
        await page.goto(URL);
        await expect(section(page).getByRole("list", { name: "Suggested keywords" })).toBeVisible();
      };
      const shot = async (page: Page, name: string, fullPage = true) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(400);
        const path = `${OUT}/${name}-${width}-${theme}.png`;
        // Phones scroll the document; from 1024px the page scrolls inside <main>, so the section alone.
        if (width < 1024) return page.screenshot({ path, fullPage });
        return section(page).screenshot({ path });
      };

      test("tracking off", async ({ page }) => {
        await open(page, { body: trackingOff });
        await expect(section(page).getByRole("heading", { name: "Confirmed · 2", exact: true })).toBeVisible();
        await shot(page, "tracking-off");
      });

      test("tracking on", async ({ page }) => {
        await open(page, { body: decided });
        await expect(section(page).getByRole("heading", { name: "Confirmed · 2 · 2 tracked" })).toBeVisible();
        await shot(page, "tracking-on");
      });

      test("relevance tooltip", async ({ page }) => {
        await open(page, { body: decided });
        const number = section(page).getByRole("list", { name: "Suggested keywords" }).getByRole("button", { name: "Relevance 0.50" }).first();
        await expect(page.getByTestId("trends-canvas")).toBeVisible();
        await page.waitForTimeout(1500); // the page settles its own scroll after load
        await number.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
        await number.focus();
        await expect(page.getByRole("tooltip")).toContainText("how many titles use the phrase and its words");
        await shot(page, "relevance-tooltip", false); // the viewport: a full-page capture resizes it, closing the tooltip
      });
    });
  }
}
