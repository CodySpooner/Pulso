import { expect, test, type Page } from "@playwright/test";

import { mockScreenerApi, rows, savedScreen } from "./fixtures";

// p4-32 (WF-1b) owner review screenshots, from fixtures only: a saved screen with unsaved changes and a score's card
// open, the first visit, and no matches; at 1440px and 375px, dark and light. Run with
// `pnpm --filter web e2e:screenshots e2e/screener`; output: docs/screenshots/p4-32/.
const OUT = "../../docs/screenshots/p4-32";
const screen = savedScreen({ filters: { margin_bps_min: 3000, lifecycle: ["emerging", "rising"], ship_days_us_max: 14 }, sort: "opportunity" });

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
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("saved screen, a NULL Trend's card open", async ({ page }) => {
        await mockScreenerApi(page, { screens: [screen], items: rows(40) });
        await page.goto(`/screener?screen=${screen.id}`);
        if (width === 1440) {
          const ship = page.getByLabel("Ship days to US, at most (days)");
          await ship.fill("10");
          await ship.press("Enter");
          const trend = page.getByRole("region", { name: "Products" }).getByRole("row").nth(1).getByRole("button", { name: /^Trend:/ });
          await trend.focus();
        } else {
          await page.getByRole("list", { name: "Products" }).getByRole("article").first().getByRole("button", { name: /^Trend:/ }).tap();
        }
        await expect(page.locator('[role="tooltip"]:not([data-state="closed"])')).toContainText("Insufficient signal.");
        await shot(page, "saved-screen");
      });

      test("first visit", async ({ page }) => {
        await mockScreenerApi(page, { items: rows(40) });
        await page.goto("/screener");
        if (width === 375) await page.getByRole("button", { name: "Filters" }).tap();
        await expect(page.getByRole("button", { name: "Landed margin ≥ 40%" }).last()).toBeVisible();
        await shot(page, "first-visit");
      });

      test("no matches", async ({ page }) => {
        await mockScreenerApi(page, { empty: true });
        await page.goto(`/screener?q=${btoa(JSON.stringify({ filters: { margin_bps_min: 9000, ship_days_us_max: 3 } })).replace(/=+$/, "")}`);
        await expect(page.getByRole("heading", { name: "No products match" })).toBeVisible();
        await shot(page, "no-matches");
      });
    });
  }
}
