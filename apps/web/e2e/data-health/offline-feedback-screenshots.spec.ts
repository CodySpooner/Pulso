import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, offlineNetwork, problem } from "./fixtures";

// imp-153, imp-157 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. A check cut off
// by the connection (the offline copy), and the locked Retry with its reason on a stale line and on a panel error.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/offline-feedback`; output: docs/screenshots/imp-153/.
const OUT = "../../docs/screenshots/imp-153";
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

async function coverageDown(page: Page, down: boolean) {
  const cov = { down };
  await page.route("**/api/v1/admin/coverage**", (route) => (cov.down ? route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }) : route.fallback()));
  return cov;
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      });

      /** `target` centred, fonts loaded, then the shot. */
      const shot = async (page: Page, name: string, target: Locator) => {
        await target.evaluate((el) => el.scrollIntoView({ block: "center" }));
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };
      /** Keyboard focus on a locked Retry opens its reason; scrolled first, since Radix closes a tooltip on scroll. */
      const shotReason = async (page: Page, name: string, retry: Locator) => {
        await retry.evaluate((el) => el.scrollIntoView({ block: "center" }));
        await page.waitForTimeout(100);
        await retry.focus();
        await expect(page.getByRole("tooltip").first()).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("import check cut off", async ({ page, context }) => {
        await mockAdminApi(page);
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "CSV import" });
        await panel.locator('input[type="file"]').setInputFiles(file);
        await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
        await setOffline(true);
        await panel.getByLabel("Source").selectOption("cj"); // checks the open file again, offline
        const retry = panel.getByRole("button", { name: "Retry" });
        await expect(retry).toBeVisible();
        await shot(page, "import", retry);
      });

      test("stale line Retry", async ({ page, context }) => {
        await mockAdminApi(page);
        const cov = await coverageDown(page, false);
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Coverage" });
        await expect(panel.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
        cov.down = true;
        await page.getByRole("button", { name: "Refresh" }).focus(); // by keyboard, so Retry's focus later shows its ring
        await page.keyboard.press("Enter");
        const retry = panel.getByRole("group", { name: "Couldn't refresh coverage" }).getByRole("button", { name: "Retry" });
        await expect(retry).toBeVisible();
        await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
        await setOffline(true);
        await shotReason(page, "stale", retry);
      });

      test("panel error Retry", async ({ page, context }) => {
        await mockAdminApi(page);
        await coverageDown(page, true);
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Coverage" });
        await expect(panel.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
        await setOffline(true);
        await shotReason(page, "panel", panel.getByRole("button", { name: "Retry" }));
      });
    });
  }
}
