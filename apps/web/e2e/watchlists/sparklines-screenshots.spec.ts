import { expect, test, type Page } from "@playwright/test";

import { CATALOG, MAIN, mockWatchlistsApi, watchStore, type WatchMock } from "./fixtures";

// imp-419 owner review screenshots, from fixtures only: the 30-day velocity sparkline column and phone cards (a gap, a
// stale row that stops 3 days ago, a late start, no source yet), the hover card with the days without data, and the
// loading placeholders. Run with `pnpm --filter web e2e:screenshots e2e/watchlists/sparklines`; output:
// docs/screenshots/imp-419/.
const OUT = "../../docs/screenshots/imp-419";

/** Main also holds product 8 (stale, its line stops 3 days ago) and 13 (tracked for 9 days). */
const store = () => {
  const s = watchStore();
  for (const i of [8, 13]) s.items.push({ list: MAIN, product_id: CATALOG[i].id, name: CATALOG[i].title, added_at: "2026-10-20T09:00:00Z" });
  return s;
};

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
      const phone = width === 375;
      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForFunction(() => [...document.querySelectorAll<HTMLElement>("main [style*='opacity']")].every((el) => el.closest("[role=status]") || getComputedStyle(el).opacity === "1"));
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };
      const open = async (page: Page, options: WatchMock = {}) => {
        await mockWatchlistsApi(page, { store: store(), ...options });
        await page.goto("/watchlists");
      };
      const spark = (page: Page, i: number) =>
        page.getByRole(phone ? "article" : "row").filter({ hasText: CATALOG[i].title }).getByRole("button", { name: /^Velocity, last 30 days/ });

      test("sparklines", async ({ page }) => {
        await open(page);
        await expect(spark(page, 3)).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
        if (!phone) {
          const region = page.getByRole("region", { name: "Main products" });
          expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
        }
        await shot(page, "list");
      });

      test("hover card with gaps", async ({ page }) => {
        await open(page);
        await spark(page, 3)[phone ? "click" : "hover"]();
        await expect(page.locator('[role="tooltip"]:not([data-state="closed"])')).toContainText("No data Oct 2 → Oct 4, Oct 15");
        await shot(page, "hint");
      });

      test("stale row", async ({ page }) => {
        await open(page);
        await spark(page, 8)[phone ? "click" : "hover"]();
        await expect(page.locator('[role="tooltip"]:not([data-state="closed"])')).toContainText("Stale");
        await shot(page, "stale");
      });

      test("loading", async ({ page }) => {
        await open(page, { holdItems: true });
        await expect(page.getByRole("status", { name: "Loading products" })).toBeVisible();
        await shot(page, "loading");
      });
    });
  }
}
