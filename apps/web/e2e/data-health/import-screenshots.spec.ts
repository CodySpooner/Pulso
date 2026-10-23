import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// P1-11b owner review screenshots of the CSV import panel, from fixtures only: 1440px and 375px, dark and
// light; a checked file with one row error, the imported result, and a source without an import adapter.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/import`; output goes to docs/screenshots/P1-11b/.
const OUT = "../../docs/screenshots/P1-11b";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`csv import ${width}px ${theme}`, async ({ page }) => {
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
        await panel.screenshot({ path: `${OUT}/import-${name}-${width}-${theme}.png` });
      };

      await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeVisible();
      await shot("ready");
      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
      await shot("preview");
      await panel.getByRole("button", { name: "Import 3 rows" }).click();
      await expect(panel).toContainText("run #501");
      await shot("done");
      await panel.getByLabel("Source").selectOption("cj");
      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(panel).toContainText("No import adapter yet");
      await shot("no-adapter");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
