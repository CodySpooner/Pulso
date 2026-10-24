import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-145 fix (imp-156, DEC-213) owner review screenshots from fixtures only: a locked Run now focused from off-screen,
// its reason still open after the focus scrolled to it. 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/focus-reason`; output goes to docs/screenshots/imp-145/.
const OUT = "../../docs/screenshots/imp-145";
const WHY = "Live collectors run only on the collector host.";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`reason after focus scroll ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      const run = page.getByRole("button", { name: "Run CJ Dropshipping now" }); // the table, or the cards below md
      await expect(run).toHaveAttribute("aria-disabled", "true");
      await page.evaluate(() => {
        const main = document.getElementById("main")!;
        main.scrollTo(0, main.scrollHeight);
        window.scrollTo(0, document.documentElement.scrollHeight);
      });
      await expect(run).not.toBeInViewport();
      await run.focus();
      await expect(run).toHaveAccessibleDescription(WHY);
      await expect(page.getByRole("tooltip", { name: WHY }).first()).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/reason-after-focus-scroll-${width}-${theme}.png` });
    });
  }
}
