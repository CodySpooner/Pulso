import { expect, test, type Page } from "@playwright/test";

import { BOARD, mockBoardsApi } from "./fixtures";

// imp-454 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. A board's card stats as a
// grid and as a table (every stat state: values, a loss, Duty not set, No source yet, Insufficient signal, stale, the
// merged note), a stat's provenance on focus, and the cards' loading and error states. Run with
// `pnpm --filter web e2e:screenshots e2e/boards/card-stats-screenshots`; output: docs/screenshots/imp-454/.
const OUT = "../../docs/screenshots/imp-454";
const Q4 = `/boards/${BOARD(1)}`;

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
      };

      test("grid", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(Q4);
        await expect(page.getByRole("button", { name: "Lifecycle stage: Rising" })).toBeVisible();
        await shot(page, "stats-grid");
      });

      test("grid, second board", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(`/boards/${BOARD(2)}`);
        await expect(page.getByRole("button", { name: "Lifecycle stage: Dead" })).toBeVisible();
        await shot(page, "stats-grid-pets");
      });

      test("table", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(`${Q4}?view=table`);
        await expect(page.getByRole("rowheader", { name: "Sunset projection lamp" })).toBeVisible();
        await shot(page, "stats-table");
      });

      test("provenance on focus", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(Q4);
        const trend = page.getByRole("article", { name: "Galaxy star projector" }).getByRole("button", { name: "Trend Score: 65" });
        await trend.scrollIntoViewIfNeeded();
        await trend.focus();
        await expect(page.locator('[role="tooltip"]:not([data-state="closed"])')).toContainText("Pulso score");
        await shot(page, "stats-provenance", false);
      });

      test("loading", async ({ page }) => {
        await mockBoardsApi(page, { holdItems: true });
        await page.goto(Q4);
        await expect(page.getByRole("status", { name: "Loading this board's products" })).toBeVisible();
        await shot(page, "stats-loading", false);
      });

      test("error", async ({ page }) => {
        await mockBoardsApi(page, { itemsStatus: 503 });
        await page.goto(Q4);
        await expect(page.getByRole("heading", { name: "Couldn't load this board's products" })).toBeVisible();
        await shot(page, "stats-error", false);
      });
    });
  }
}
