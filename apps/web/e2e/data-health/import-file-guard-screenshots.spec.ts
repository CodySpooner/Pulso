import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-092 owner review screenshots of the CSV import panel, from fixtures only: 1440px and 375px, dark and light.
// "locked": an import is running, a dropped file was refused and the keyboard is on the unavailable Choose
// another…. "done": the original import's outcome and Open runs. Run with
// `pnpm --filter web e2e:screenshots e2e/data-health/import-file-guard`.
const OUT = "../../docs/screenshots/imp-092";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`csv import file guard ${width}px ${theme}`, async ({ page }) => {
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
      const input = panel.locator('input[type="file"]');
      const shot = async (name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await panel.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
        await page.waitForTimeout(300);
        await panel.screenshot({ path: `${OUT}/import-${name}-${width}-${theme}.png` });
      };

      await input.setInputFiles(file);
      await panel.getByRole("button", { name: "Import 3 rows" }).focus();
      await page.keyboard.press("Enter");
      await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
      const dataTransfer = await page.evaluateHandle(() => {
        const dt = new DataTransfer();
        dt.items.add(new File(["date,base,quote,rate\n"], "other.csv", { type: "text/csv" }));
        return dt;
      });
      await input.locator("..").dispatchEvent("dragover", { dataTransfer });
      await input.locator("..").dispatchEvent("drop", { dataTransfer }); // refused: rates.csv keeps importing
      await page.keyboard.press("Shift+Tab");
      await expect(panel.getByRole("button", { name: "Choose another…" })).toBeFocused();
      await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
      await shot("locked");

      release();
      await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501/);
      await shot("done");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
