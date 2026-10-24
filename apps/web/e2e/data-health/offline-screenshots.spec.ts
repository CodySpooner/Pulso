import { expect, test, type Locator } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-134 owner review screenshots of the offline state, from fixtures only: 1440px and 375px, dark and light. The
// banner with Refresh's reason, a source switch's reason, and Import's reason line under a checked file.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/offline`; output: docs/screenshots/imp-134/.
const OUT = "../../docs/screenshots/imp-134";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`offline ${width}px ${theme}`, async ({ page, context }) => {
      await mockAdminApi(page, { host: { live_runs_allowed: true } });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "CSV import" });
      await panel.locator('input[type="file"]').setInputFiles(file);
      await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
      await context.setOffline(true);
      await expect(page.getByRole("status").filter({ hasText: "You're offline." })).toBeVisible();

      /** Keyboard focus on `control` opens its reason; scrolled first, since Radix closes a tooltip on scroll. */
      const shot = async (name: string, control: Locator, block: ScrollLogicalPosition) => {
        await control.evaluate((el, b) => el.scrollIntoView({ block: b }), block);
        await page.waitForTimeout(100);
        await control.focus();
        await expect(page.getByRole("tooltip").first()).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
        await control.blur();
      };

      await shot("banner", page.getByRole("button", { name: "Refresh" }), "end");
      // Below lg the banner sticks under the top bar, so it is still on screen beside a switch further down.
      await shot("switch", page.getByRole("switch", { name: "CJ Dropshipping enabled" }), "center");

      await panel.getByRole("button", { name: "Import 3 rows" }).evaluate((el) => el.scrollIntoView({ block: "center" }));
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/import-${width}-${theme}.png` });
    });
  }
}
