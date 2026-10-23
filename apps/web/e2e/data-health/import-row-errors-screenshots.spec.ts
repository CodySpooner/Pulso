import { expect, test } from "@playwright/test";

import { cjPreview, mockAdminApi } from "./fixtures";

// imp-116 owner review screenshots of the Row errors table, from fixtures only: 1440px and 375px, dark and light;
// CJ (check only) with its 2 row errors under the heading, then Frankfurter FX after an import that skipped a row,
// keyboard-focused. Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-row-errors`; output goes
// to docs/screenshots/imp-116/.
const OUT = "../../docs/screenshots/imp-116";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-10-20,USD,JPY,150.25\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 1400], // phone width; tall enough that the whole panel fits under the fixed app header and nav
  ]) {
    test(`csv import row errors ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "CSV import" });
      const shot = async (name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await panel.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
        await page.waitForTimeout(300);
        await panel.screenshot({ path: `${OUT}/import-row-errors-${name}-${width}-${theme}.png` });
      };

      await page.route(/\/import\/preview$/, (route) => route.fulfill({ json: cjPreview }));
      await panel.getByLabel("Source").selectOption("cj");
      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(panel.getByRole("heading", { name: "Row errors" })).toBeVisible();
      await shot("cj-check");

      await page.unroute(/\/import\/preview$/);
      await panel.getByLabel("Source").selectOption("fx_frankfurter");
      await panel.getByRole("button", { name: "Import 3 rows" }).focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("button", { name: "Open runs" })).toBeFocused();
      await page.keyboard.press("Tab"); // the skipped rows, right after Open runs
      await expect(panel.getByRole("region", { name: "Row errors" })).toBeFocused();
      await shot("fx-imported");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
