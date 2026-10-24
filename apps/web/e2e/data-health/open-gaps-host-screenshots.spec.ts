import { expect, test } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-145 + imp-146 owner review screenshots from fixtures only: the Coverage panel with GET /host 503 (the gap
// check line, no list) and with GET /coverage 503 (Open gaps still listed). 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/open-gaps-host`; output goes to docs/screenshots/imp-145/.
const OUT = "../../docs/screenshots/imp-145";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    for (const failing of ["host", "coverage"] as const) {
      test(`${failing} 503 ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page);
        await page.route(
          (url) => url.pathname === `/api/v1/admin/${failing}`,
          (route) => route.fulfill({ status: 503, json: problem(503, `req_${failing}_503`) }),
        );
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Coverage", exact: true });
        await expect(panel).toContainText(failing === "host" ? "Gap check didn't load" : "Couldn't load coverage");
        if (failing === "coverage") await expect(panel.getByRole("region", { name: "Open gaps" })).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        // Grow the viewport to the content so the fixed phone bars don't cover the panel.
        const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
        await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
        await page.waitForTimeout(400);
        await panel.screenshot({ path: `${OUT}/${failing}-503-coverage-${width}-${theme}.png` });
      });
    }
  }
}
