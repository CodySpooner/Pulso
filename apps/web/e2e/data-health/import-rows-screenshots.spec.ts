import { expect, test } from "@playwright/test";

import { cjPreview, mockAdminApi } from "./fixtures";

// imp-080 owner review screenshots of the parsed row sample, from fixtures only: 1440px and 375px, dark and
// light; Frankfurter FX with all 3 valid rows, and CJ (check only) with the first 20 of 1,284, keyboard-focused.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-rows`; output goes to docs/screenshots/imp-080/.
const OUT = "../../docs/screenshots/imp-080";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-10-20,USD,JPY,150.25\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 1400], // phone width; tall enough that the whole panel fits under the fixed app header and nav
  ]) {
    test(`csv import row sample ${width}px ${theme}`, async ({ page }) => {
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
        await panel.screenshot({ path: `${OUT}/import-rows-${name}-${width}-${theme}.png` });
      };

      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(panel.getByRole("region", { name: "Valid rows · all 3" })).toBeVisible();
      await shot("fx-all");

      await page.route(/\/import\/preview$/, (route) => route.fulfill({ json: cjPreview }));
      await panel.getByLabel("Source").selectOption("cj");
      const sample = panel.getByRole("region", { name: "Valid rows · first 20 of 1,284" });
      await panel.getByRole("button", { name: "Import 1,284 rows" }).focus();
      await page.keyboard.press("Tab");
      await expect(sample).toBeFocused();
      await shot("cj-first-20");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
