import { expect, test, type Page } from "@playwright/test";

import { firstRun, mockSettingsApi } from "../settings/fixtures";
import { mockProductApi, overviewNoDuty, overviewUnmatched, PRODUCT_ID } from "./fixtures";

// imp-368 owner review screenshots, from fixtures only, at 1440px and 375px, dark and light: a withheld margin's next
// action (duty, focused by keyboard; no supplier), then Settings as "Set duty" lands, the rate open and focused.
// Run with `pnpm --filter web e2e:screenshots e2e/products/overview-next-action-screenshots`; output: docs/screenshots/imp-368/.
const OUT = "../../docs/screenshots/imp-368";
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
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage: true });
      };

      test("duty not set, action focused", async ({ page }) => {
        await mockProductApi(page, { overview: overviewNoDuty });
        await page.goto(URL);
        await page.getByRole("button", { name: "Landed margin: Duty not set" }).focus();
        await page.keyboard.press("Tab");
        await expect(page.getByRole("link", { name: "Set duty" })).toBeFocused();
        await shot(page, "duty-action");
      });

      test("no supplier", async ({ page }) => {
        await mockProductApi(page, { overview: overviewUnmatched });
        await page.goto(URL);
        await expect(page.getByRole("button", { name: "Open Suppliers" })).toBeVisible();
        await shot(page, "suppliers-action");
      });

      test("settings, arrived for duty", async ({ page }) => {
        await mockProductApi(page, { overview: overviewNoDuty });
        await mockSettingsApi(page, { settings: firstRun });
        await page.goto(URL);
        await page.getByRole("link", { name: "Set duty" }).click();
        await expect(page.getByRole("textbox", { name: /^Default duty rate/ })).toBeFocused();
        await page.screenshot({ path: `${OUT}/settings-duty-${width}-${theme}.png` }); // the viewport: where the scroll landed
      });
    });
  }
}
