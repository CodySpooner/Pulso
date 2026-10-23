import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-082 review screenshots from fixtures only: the first-load skeletons and the loaded page at the same
// size, 1440px and 375px, dark and light. Run with `pnpm --filter web e2e:screenshots e2e/data-health/loading`.
const OUT = "../../docs/screenshots/imp-082";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`first load ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { delayMs: 8000 });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await expect(page.getByRole("region", { name: "Sources", exact: true }).locator(".bg-skeleton:visible").first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      // From 1024px the page scrolls inside <main>, so fullPage can't see it: grow the viewport instead.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/loading-${width}-${theme}.png`, fullPage: width < 1024 });

      await expect(page.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible({ timeout: 15_000 });
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/loaded-${width}-${theme}.png`, fullPage: width < 1024 });
    });
  }
}
