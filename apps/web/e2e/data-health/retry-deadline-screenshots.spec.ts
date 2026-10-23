import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-094 owner review screenshots from fixtures only (now 14:00 UTC, Shopify retry not before 15:00 UTC):
// the Sources panel and the re-enable dialog, at 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/retry-deadline`; output goes to docs/screenshots/imp-094/.
const OUT = "../../docs/screenshots/imp-094";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`sources panel ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "Sources", exact: true });
      await expect(panel).toContainText("5 consecutive 429 responses");
      await page.evaluate(() => document.fonts.ready);
      // Grow the viewport to the content so the fixed phone bars don't cover the panel.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await panel.screenshot({ path: `${OUT}/sources-${width}-${theme}.png` });
    });

    test(`re-enable dialog ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await page.getByRole("switch", { name: "Shopify stores enabled" }).locator("visible=true").click();
      await expect(page.getByRole("dialog", { name: "Re-enable Shopify stores?" })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/reenable-dialog-${width}-${theme}.png` });
    });
  }
}
