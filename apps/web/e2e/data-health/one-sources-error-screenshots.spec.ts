import { expect, test } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-139 owner review screenshots from fixtures only: GET /sources 503 with one error in the Sources panel, the
// Coverage rows by key under their line, and the CSV import line. The full page, then each dependent panel.
// 1440px and 375px, dark and light. Before: docs/screenshots/aud-014/r3a-sources-503-*.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/one-sources-error`; output goes to docs/screenshots/imp-139/.
const OUT = "../../docs/screenshots/imp-139";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`sources 503 ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.route(
        (url) => url.pathname === "/api/v1/admin/sources",
        (route) => route.fulfill({ status: 503, json: problem(503, "req_sources_503") }),
      );
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const panel = (name: string) => page.getByRole("region", { name, exact: true });
      await expect(panel("Sources").getByRole("button", { name: "Retry" })).toBeVisible({ timeout: 15_000 });
      await expect(panel("CSV import")).toContainText("Waits for the source list above.");
      await page.evaluate(() => document.fonts.ready);
      // Grow the viewport to the content so the fixed phone bars don't cover the panels.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/sources-503-page-${width}-${theme}.png`, fullPage: true });
      await panel("Coverage").screenshot({ path: `${OUT}/sources-503-coverage-${width}-${theme}.png` });
      await panel("CSV import").screenshot({ path: `${OUT}/sources-503-import-${width}-${theme}.png` });
    });
  }
}
