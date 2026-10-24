import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, offlineNetwork, problem } from "./fixtures";

// imp-173, imp-175 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. A locked Run now
// whose reason stays open after Enter (1440) or a second tap (375), and the offline Retry reasons below their button,
// clear of the Error ID line, on a stale line and on a panel error.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/tap-tooltip`; output: docs/screenshots/imp-173/.
const OUT = "../../docs/screenshots/imp-173";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ hasTouch: width === 375 });
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      });

      const shot = async (page: Page, name: string) => {
        await expect(page.locator('[role="tooltip"][data-state$="-open"]')).toHaveCount(1);
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };
      /** Keyboard focus on a locked Retry opens its reason; scrolled first, so the shot frames it. */
      const focusReason = async (page: Page, retry: Locator) => {
        await retry.evaluate((el) => el.scrollIntoView({ block: "center" }));
        await retry.focus();
      };

      test("press keeps the reason", async ({ page }) => {
        await mockAdminApi(page);
        await page.goto("/admin/data-health");
        const run = page.getByRole("button", { name: "Run CJ Dropshipping now" }).locator("visible=true");
        await run.evaluate((el) => el.scrollIntoView({ block: "center" }));
        if (width === 375) {
          await run.tap({ force: true });
          await run.tap({ force: true });
        } else {
          await run.focus();
          await page.keyboard.press("Enter");
        }
        await expect(run).toHaveAttribute("data-state", /-open$/);
        await shot(page, "run-pressed");
      });

      test("stale line Retry", async ({ page, context }) => {
        const cov = { down: false };
        await mockAdminApi(page);
        await page.route("**/api/v1/admin/coverage**", (route) => (cov.down ? route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }) : route.fallback()));
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Coverage" });
        await expect(panel.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
        cov.down = true;
        await page.getByRole("button", { name: "Refresh" }).focus(); // by keyboard, so Retry's focus later shows its ring
        await page.keyboard.press("Enter");
        const retry = panel.getByRole("group", { name: "Couldn't refresh coverage" }).getByRole("button", { name: "Retry" });
        await expect(retry).toBeVisible();
        await setOffline(true);
        await focusReason(page, retry);
        await shot(page, "stale");
      });

      test("panel error Retry", async ({ page, context }) => {
        await mockAdminApi(page);
        await page.route("**/api/v1/admin/coverage**", (route) => route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }));
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Coverage" });
        await expect(panel.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
        await setOffline(true);
        await focusReason(page, panel.getByRole("button", { name: "Retry" }));
        await shot(page, "panel");
      });
    });
  }
}
