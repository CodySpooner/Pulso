import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-168 owner review screenshots from fixtures only: where focus lands after a keyboard Retry in the run drawer.
// A failed runs or targets Retry (Retry again, announced once) and one that restores the runs (the drawer title).
// 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/drawer-retry`; output goes to docs/screenshots/imp-168/.
const OUT = "../../docs/screenshots/imp-168";
const RUNS = (url: URL) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj";
const TARGETS = "**/api/v1/admin/runs/418"; // CJ's newest run, which opens expanded

async function open(page: Page, width: number, height: number, theme: string, failing: typeof RUNS | string) {
  await mockAdminApi(page);
  const api = { down: true };
  await page.route(failing, (route) => (api.down ? route.fulfill({ status: 503, json: problem(503, "req-7f3a") }) : route.fallback()));
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
  const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
  const retry = drawer.getByRole("button", { name: "Retry" });
  await retry.focus();
  return { api, drawer, retry };
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
    for (const [what, failing] of [
      ["runs", RUNS],
      ["targets", TARGETS],
    ] as const) {
      test(`drawer ${what} Retry failed ${width}px ${theme}`, async ({ page }) => {
        const { drawer, retry } = await open(page, width, height, theme, failing);
        await page.keyboard.press("Enter");
        await expect(drawer.getByRole("alert").filter({ hasText: `Couldn't load ${what}.` })).toHaveCount(1);
        await expect(retry).toBeFocused();
        await shoot(page, `drawer-${what}-retry-failed-${width}-${theme}`);
      });
    }

    test(`drawer runs Retry restored ${width}px ${theme}`, async ({ page }) => {
      const { api, drawer } = await open(page, width, height, theme, RUNS);
      api.down = false;
      await page.keyboard.press("Enter");
      await expect(drawer.getByRole("heading", { level: 2, name: "CJ Dropshipping" })).toBeFocused();
      await expect(drawer.getByRole("list", { name: "CJ Dropshipping runs" })).toBeVisible();
      await shoot(page, `drawer-runs-retry-restored-${width}-${theme}`);
    });
  }
}
