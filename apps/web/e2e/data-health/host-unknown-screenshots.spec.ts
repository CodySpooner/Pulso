import { expect, test } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-133 owner review screenshots from fixtures only: GET /host answers 503 while sources answer 200, so the
// Sources panel reads Unknown with the gap-check reason and counts floors. 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/host-unknown`; output goes to docs/screenshots/imp-133/.
const OUT = "../../docs/screenshots/imp-133";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`host 503 ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.route(
        (url) => url.pathname === "/api/v1/admin/host",
        (route) => route.fulfill({ status: 503, json: problem(503, "req_host_503") }),
      );
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await expect(page.getByRole("region", { name: "Sources", exact: true })).toContainText("at least 1 needs attention");
      await page.evaluate(() => document.fonts.ready);
      // Grow the viewport to the content so the fixed phone bars don't cover the panels.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/host-503-${width}-${theme}.png` });
      await page.getByRole("region", { name: "Sources", exact: true }).screenshot({ path: `${OUT}/sources-${width}-${theme}.png` });
    });
  }
}
