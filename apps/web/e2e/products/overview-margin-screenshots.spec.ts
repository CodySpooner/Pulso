import { expect, test, type Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";
import { mockProductApi, overview, overviewNoDuty, overviewUnmatched, PRODUCT_ID } from "./fixtures";

// imp-280 owner review screenshots, from fixtures only: the Overview's landed margin at 1440px and 375px, dark and light.
// Discover's margin with its provenance card open, then duty not set, no supplier pick and a stale input.
// Run with `pnpm --filter web e2e:screenshots e2e/products/overview-margin-screenshots`; output: docs/screenshots/imp-280/.
const OUT = "../../docs/screenshots/imp-280";
const URL = `/products/${PRODUCT_ID}`;
const margin = overview.landed_margin_minor as components["schemas"]["Margin"];
// Its oldest input three days older: past twice CJ's interval.
const stale = { ...overview, landed_margin_minor: { ...margin, as_of: new Date(Date.parse(margin.as_of) - 3 * 86_400_000).toISOString(), stale: true } };

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

      test("margin, card open", async ({ page }) => {
        await mockProductApi(page);
        await page.goto(URL);
        const value = page.getByRole("button", { name: "Landed margin: $11.88" });
        if (width === 375) await value.tap();
        else await value.focus();
        await expect(page.locator('[role="tooltip"]')).toContainText("Raw payload");
        await shot(page, "margin");
      });

      test("duty not set", async ({ page }) => {
        await mockProductApi(page, { overview: overviewNoDuty });
        await page.goto(URL);
        await expect(page.getByText("Needs a duty rate.")).toBeVisible();
        await shot(page, "duty-not-set");
      });

      test("no supplier pick", async ({ page }) => {
        await mockProductApi(page, { overview: overviewUnmatched });
        await page.goto(URL);
        await expect(page.getByText("Needs a market price, a supplier price and a freight quote.")).toBeVisible();
        await shot(page, "no-supplier");
      });

      test("stale input", async ({ page }) => {
        await mockProductApi(page, { overview: stale });
        await page.goto(URL);
        await expect(page.getByText("CJ Dropshipping · 3d ago · stale")).toBeVisible();
        await shot(page, "stale");
      });
    });
  }
}
