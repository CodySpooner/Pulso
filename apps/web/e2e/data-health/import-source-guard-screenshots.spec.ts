import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-089 owner review screenshots of the CSV import panel, from fixtures only: 1440px and 375px, dark and light.
// "locked": an import is running and the keyboard is on the unavailable Source select. "done": it finished, the
// select works again. Run with `pnpm --filter web e2e:screenshots e2e/data-health/import-source-guard`.
const OUT = "../../docs/screenshots/imp-089";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`csv import source guard ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      let release!: () => void;
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route(/\/sources\/[^/]+\/import$/, async (route) => {
        await held;
        await route.fallback();
      });
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

      await panel.locator('input[type="file"]').setInputFiles(file);
      await panel.getByRole("button", { name: "Import 3 rows" }).click();
      await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
      const select = panel.getByLabel("Source");
      await select.focus();
      await page.keyboard.press("ArrowUp"); // ignored: the ring stays on Frankfurter FX
      await expect(select).toHaveValue("fx_frankfurter");
      await shot("locked");

      release();
      await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501/);
      await expect(select).toHaveAttribute("aria-disabled", "false");
      await shot("done");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
