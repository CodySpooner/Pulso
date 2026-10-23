import { expect, test } from "@playwright/test";

import { mockAdminApi, sources } from "./fixtures";

// imp-081 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The row actions
// (one source without a template), the panel a row opened by keyboard, and the switch question for an open file.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-entry`; output goes to docs/screenshots/imp-081/.
const OUT = "../../docs/screenshots/imp-081";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const noTemplate = sources.map((s) => (s.key === "google_trends" ? { ...s, csv_import: null } : s));

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`import entry ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { sources: noTemplate });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const table = page.getByRole("region", { name: "Sources", exact: true });
      const panel = page.getByRole("region", { name: "CSV import" });
      const settle = async () => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
      };

      // The row actions; the source without a template explains itself on focus.
      await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeVisible();
      const none = page.getByRole("button", { name: "Import CSV for Google Trends" });
      await none.evaluate((el) => el.scrollIntoView({ block: "center" })); // before focus: scrolling closes a tooltip
      await none.focus();
      await expect(page.getByRole("tooltip")).toBeVisible();
      await settle();
      await page.screenshot({ path: `${OUT}/entry-rows-${width}-${theme}.png` });
      await table.screenshot({ path: `${OUT}/entry-sources-${width}-${theme}.png` });

      // Keyboard: CJ's Check CSV lands on Choose CSV… with CJ's template and the "no adapter" reason.
      await page.getByRole("button", { name: "Check CSV for CJ Dropshipping" }).focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeFocused();
      await settle();
      await page.screenshot({ path: `${OUT}/entry-opened-${width}-${theme}.png` });

      // An open file: the panel asks before switching to Frankfurter FX.
      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
      await page.getByRole("button", { name: "Import CSV for Frankfurter FX" }).focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("button", { name: "Switch to Frankfurter FX" })).toBeFocused();
      await settle();
      await panel.screenshot({ path: `${OUT}/entry-switch-ask-${width}-${theme}.png` });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
