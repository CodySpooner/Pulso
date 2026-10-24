import { expect, test, type Page, type Route } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-135 (aud-014 A14-04) owner review screenshots from fixtures only: where focus lands after a keyboard Retry.
// The page-level Retry that succeeds (the Collector host heading), the one that fails (Retry again), and a panel
// Retry that succeeds (the Coverage heading). 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/retry-focus`; output goes to docs/screenshots/imp-135/.
const OUT = "../../docs/screenshots/imp-135";
const API = "**/api/v1/admin/**";

async function open(page: Page, width: number, height: number, theme: string, failing: string) {
  await mockAdminApi(page);
  const api = { down: true };
  // The whole API down fails without an answer (the API-down page); a single panel's call answers 503.
  const fail = failing === API ? (route: Route) => route.abort("connectionrefused") : (route: Route) => route.fulfill({ status: 503, json: problem(503, "req-7f3a") });
  await page.route(failing, (route) => (api.down ? fail(route) : route.fallback()));
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  return api;
}

async function shoot(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`page Retry restored ${width}px ${theme}`, async ({ page }) => {
      const api = await open(page, width, height, theme, API);
      const retry = page.getByRole("button", { name: "Retry" });
      await retry.focus();
      api.down = false;
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 2, name: "Collector host" })).toBeFocused();
      await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
      await shoot(page, `page-retry-restored-${width}-${theme}`);
    });

    test(`page Retry failed ${width}px ${theme}`, async ({ page }) => {
      await open(page, width, height, theme, API);
      const retry = page.getByRole("button", { name: "Retry" });
      await retry.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("button", { name: "Refreshing…" })).toBeVisible();
      await expect(retry).toBeFocused();
      await expect(page.getByRole("alert").filter({ hasText: "Can't reach the API." })).toHaveCount(1);
      await shoot(page, `page-retry-failed-${width}-${theme}`);
    });

    test(`coverage Retry restored ${width}px ${theme}`, async ({ page }) => {
      const api = await open(page, width, height, theme, "**/api/v1/admin/coverage**");
      const coverage = page.getByRole("region", { name: "Coverage" });
      await coverage.getByRole("button", { name: "Retry" }).focus();
      api.down = false;
      await page.keyboard.press("Enter");
      await expect(coverage.getByRole("heading", { level: 2, name: "Coverage" })).toBeFocused();
      await expect(coverage.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
      await shoot(page, `coverage-retry-restored-${width}-${theme}`);
    });
  }
}
