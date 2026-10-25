import { expect, test, type Page } from "@playwright/test";

import { mockProductAmazonApi, noImport, noSource, notRanked, ranked, staleRanks, type AmazonRanksMock } from "./amazon-fixtures";
import { mockProductApi, PRODUCT_ID } from "./fixtures";

// p3-07 (AMZ-1c) owner review screenshots, from fixtures only: the Trends tab's Amazon ranks section at 1440px and
// 375px, dark and light, in every state, plus keyboard focus on its link. Each shot asserts no sideways page scroll.
// Run with `pnpm --filter web e2e:screenshots e2e/products/amazon-screenshots`; output: docs/screenshots/p3-07/.
const OUT = "../../docs/screenshots/p3-07";
const URL = `/products/${PRODUCT_ID}?tab=trends`;
const section = (page: Page) => page.getByRole("region", { name: "Amazon ranks" });

const STATES: [string, AmazonRanksMock, string][] = [
  ["ranked", { body: ranked }, "Amazon · manual import, as of Oct 21, 2026"],
  ["not-ranked", { body: notRanked }, "Not in an imported Amazon list."],
  ["no-import", { body: noImport }, "No Amazon import yet."],
  ["no-source", { body: noSource }, "Amazon: no source yet."],
  ["stale", { body: staleRanks }, "17 days ago"],
  ["error", { status: 503 }, "Couldn't load Amazon ranks"],
];

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
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
        await section(page).screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      for (const [name, options, text] of STATES)
        test(name, async ({ page }) => {
          await mockProductAmazonApi(page, options);
          await page.goto(URL);
          await expect(section(page).getByText(text)).toBeVisible();
          await shot(page, name);
        });

      test("loading", async ({ page }) => {
        await mockProductAmazonApi(page, { hold: true });
        await page.goto(URL);
        await expect(section(page).getByLabel("Loading Amazon ranks")).toBeVisible();
        await shot(page, "loading");
      });

      test("keyboard focus", async ({ page }) => {
        await mockProductAmazonApi(page);
        await page.goto(URL);
        await expect(section(page).getByRole("table")).toBeVisible();
        await section(page).getByRole("link", { name: "Every Amazon list" }).focus();
        await shot(page, "focus");
      });
    });
  }
}
