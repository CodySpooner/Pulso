import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-069 owner review screenshots from fixtures only: the Coverage panel's open-gaps table, which cues hidden
// columns at 375px (and again on the left once scrolled) and shows no cue at 1440px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/scroll-cue`; output goes to docs/screenshots/imp-069/.
const OUT = "../../docs/screenshots/imp-069";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`open gaps ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = page.getByRole("region", { name: "Coverage", exact: true });
      const gaps = panel.getByRole("region", { name: "Open gaps" });
      await expect(gaps).toContainText("Host offline");
      await page.evaluate(() => document.fonts.ready);
      // Grow the viewport to the content so the fixed phone bars don't cover the panel.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await panel.screenshot({ path: `${OUT}/open-gaps-${width}-${theme}.png` });
      if (width > 375) return;

      await gaps.evaluate((el) => el.scrollTo({ left: el.scrollWidth }));
      await expect(page.locator('[data-scroll-cue="left"]')).toBeVisible();
      await panel.screenshot({ path: `${OUT}/open-gaps-scrolled-${width}-${theme}.png` });
    });
  }
}
