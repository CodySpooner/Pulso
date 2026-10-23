import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-147 owner review screenshots from fixtures only: Data Health right after a fragment jump to Open gaps.
// At 1440 the shell stays put and only main scrolls; at 375 the sticky top bar stays at the top.
// Run with `pnpm --filter web e2e:screenshots e2e/shell-scroll`; output goes to docs/screenshots/imp-147/.
const OUT = "../../docs/screenshots/imp-147";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`jump to Open gaps ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const heading = page.getByRole("heading", { name: /^Open gaps/ });
      await expect(heading).toBeVisible();
      await expect(page.getByRole("region", { name: "CSV import" })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => (location.hash = "open-gaps"));
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/jump-${width}-${theme}.png` });
    });
  }
}
