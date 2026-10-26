import { expect, test, type Page } from "@playwright/test";

import { mockExport } from "../discover/export-fixtures";
import { mockTestingApi } from "./fixtures";

// p4-30 (WF-7b) owner review screenshots, from fixtures only: the Testing Board's Export CSV focused by keyboard,
// preparing, failed with Retry, and locked with no tests; 1440px and 375px, dark and light. Run with
// `pnpm --filter web e2e:screenshots e2e/testing/export-screenshots`; output: docs/screenshots/p4-30/.
const OUT = "../../docs/screenshots/p4-30";
const TESTS = { path: "/api/v1/tests", file: "pulso_testing.csv" };
const exportButton = (page: Page) => page.getByRole("button", { name: /^(Export CSV|Preparing)/ });

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

      test("board, Export CSV focused", async ({ page }) => {
        await mockTestingApi(page);
        await mockExport(page, ["file"], TESTS);
        await page.goto("/testing");
        await expect(page.getByRole("article", { name: "Sunset projection lamp" })).toBeVisible();
        await page.getByRole("heading", { level: 1, name: "Testing" }).focus();
        await page.keyboard.press("Tab");
        await expect(exportButton(page)).toBeFocused();
        await shot(page, "export-focus");
      });

      test("preparing", async ({ page }) => {
        await mockTestingApi(page);
        await mockExport(page, ["hold"], TESTS);
        await page.goto("/testing");
        await exportButton(page).click();
        await expect(exportButton(page)).toHaveAttribute("aria-disabled", "true");
        await shot(page, "export-preparing");
      });

      test("failed, with Retry", async ({ page }) => {
        await mockTestingApi(page);
        await mockExport(page, ["down"], TESTS);
        await page.goto("/testing");
        await exportButton(page).click();
        await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
        await shot(page, "export-failed");
      });

      test("no tests, locked", async ({ page }) => {
        await mockTestingApi(page, { items: [] });
        await page.goto("/testing");
        await expect(page.getByRole("heading", { name: /No tests yet/ })).toBeVisible();
        await exportButton(page).focus();
        await expect(page.getByRole("tooltip")).toHaveText("Nothing to export");
        await shot(page, "export-empty");
      });
    });
  }
}
