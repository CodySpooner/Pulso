import { expect, test } from "@playwright/test";

import { mockAdminApi, suppressedSources } from "./fixtures";

// imp-042 owner review screenshots from fixtures only: the Sources panel with CJ's latest slot suppressed
// (DEC-108), at 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/skipped`; output goes to docs/screenshots/imp-042/.
const OUT = "../../docs/screenshots/imp-042";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`skipped source ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { sources: suppressedSources });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "Sources", exact: true });
      await expect(panel).toContainText("Run #419 was still active");
      await page.evaluate(() => document.fonts.ready);
      // Grow the viewport to the content so the fixed phone bars don't cover the panel.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await panel.screenshot({ path: `${OUT}/sources-skipped-${width}-${theme}.png` });
    });

    test(`skipped run drawer ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { sources: suppressedSources });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).first().click();
      await expect(page.getByRole("dialog", { name: "CJ Dropshipping" })).toContainText("Run #419 was still active.");
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/run-drawer-skipped-${width}-${theme}.png` });
    });
  }
}
