import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, NOW, offlineNetwork, problem, sources } from "./fixtures";

// imp-154, imp-186, imp-187 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. Offline
// reasons that name their action, each open where it covers nothing: a stale line's Retry (above when wide, on the
// actions row's left on a phone), the run drawer's stale-line Retry (left), Run now (above in the table, below on a
// phone card) and the CSV import panel's Choose another… with Import's reason line.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/offline-reasons`; output: docs/screenshots/imp-154/.
const OUT = "../../docs/screenshots/imp-154";

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
        await retry.evaluate((el) => el.scrollIntoView({ block: "center" }));
        await retry.focus();
        await shot(page, "stale");
      });

      test("run drawer stale line Retry", async ({ page, context }) => {
        const cjRun = sources.find((s) => s.key === "cj")!.last_run!;
        const runs = { down: false };
        await mockAdminApi(page);
        await page.route(
          (url) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj",
          (route) =>
            runs.down
              ? route.fulfill({ status: 503, json: problem(503, "req-runs-1") })
              : route.fulfill({ json: { items: [cjRun], next_cursor: String(cjRun.id) } }),
        );
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
        const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
        await expect(drawer.getByRole("button", { name: "Load older runs" })).toBeVisible();
        // The drawer's stale line is a failed refresh of the loaded runs; an older page fails at the list's foot (DEC-236 a).
        runs.down = true;
        await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000)); // past the 5-minute staleTime
        await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange"))); // the tab refocuses: a refetch
        const retry = drawer.getByRole("group", { name: "Couldn't refresh runs" }).getByRole("button", { name: "Retry" });
        await expect(retry).toBeVisible();
        await setOffline(true);
        await page.keyboard.press("Shift"); // a key, so the focus below shows its ring
        await retry.focus();
        await shot(page, "drawer-stale");
      });

      test("Run now offline", async ({ page, context }) => {
        await mockAdminApi(page, { host: { live_runs_allowed: true } }); // so offline is the reason
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const run = page.getByRole("button", { name: "Run CJ Dropshipping now" }).locator("visible=true");
        await expect(run).toBeVisible();
        await setOffline(true);
        await run.evaluate((el) => el.scrollIntoView({ block: "center" }));
        if (width === 375) await run.tap({ force: true });
        else {
          await page.getByRole("button", { name: "Refresh" }).focus();
          await page.keyboard.press("Shift"); // a key, so the focus below shows its ring
          await run.focus();
        }
        await expect(run).toHaveAttribute("data-state", /-open$/);
        await shot(page, "run");
      });

      test("CSV import offline", async ({ page, context }) => {
        await mockAdminApi(page);
        const { setOffline } = await offlineNetwork(page, context);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "CSV import" });
        await panel.locator('input[type="file"]').setInputFiles({ name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") });
        await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
        await setOffline(true);
        const choose = panel.getByRole("button", { name: "Choose another…" });
        await choose.evaluate((el) => el.scrollIntoView({ block: "center" }));
        if (width === 375) await choose.tap({ force: true });
        else {
          await page.keyboard.press("Shift");
          await choose.focus();
        }
        await shot(page, "import");
      });
    });
  }
}
