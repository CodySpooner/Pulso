import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-095 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. Keyboard focus on the
// locked Import button while a held import runs ("Importing…"), and on the Import button a source blocks.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-focus-ring`; output: docs/screenshots/imp-095/.
const OUT = "../../docs/screenshots/imp-095";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`csv import focus ring ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.route(/\/sources\/[^/]+\/import$/, () => {}); // held: the import stays running
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

      const choose = panel.getByRole("button", { name: "Choose CSV…" });
      await choose.focus();
      const chooser = page.waitForEvent("filechooser");
      await page.keyboard.press("Enter");
      await (await chooser).setFiles(file);

      // A source without an import adapter blocks Import; it stays focusable with a full ring.
      await panel.getByLabel("Source").selectOption("shopify_stores");
      const importButton = panel.getByRole("button", { name: "Import 3 rows" });
      await expect(importButton).toHaveAttribute("aria-disabled", "true");
      await importButton.focus();
      await shot("blocked");

      await panel.getByLabel("Source").selectOption("fx_frankfurter");
      await expect(importButton).toHaveAttribute("aria-disabled", "false");
      await importButton.focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("button", { name: "Importing…" })).toBeFocused();
      await shot("importing");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
