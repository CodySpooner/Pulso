import { expect, test, type Locator, type Page } from "@playwright/test";

import { manyGaps, manyTargets, mockAdminApi, problem } from "./fixtures";

// imp-112 + imp-118 + imp-120 owner review screenshots from fixtures only, 1440px and 375px, dark and light: the
// open-gaps and run-targets footers after a failed page (a named Retry, "loaded" in the footer note only), the
// API-down page (its Retry the only action), and the Sources row's retry deadline with its relative hint.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/copy-hints`; output goes to docs/screenshots/imp-112/.
const OUT = "../../docs/screenshots/imp-112";

async function open(page: Page, width: number, height: number, theme: string) {
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
}

/** The viewport around `target`: an element shot taller than a phone's viewport would stitch the sticky bars over it. */
async function shoot(page: Page, target: Locator, name: string) {
  await target.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`open gaps failed page ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { gaps: manyGaps(260) });
      await page.route("**/api/v1/admin/host?*", (route) => route.fulfill({ status: 503, json: problem(503, "req_7f3a91c2") }));
      await open(page, width, height, theme);
      const panel = page.getByRole("region", { name: "Coverage" });
      await panel.getByRole("button", { name: "Load older gaps" }).focus();
      await page.keyboard.press("Enter"); // by keyboard, so the named Retry shows its focus ring
      const retry = panel.getByRole("button", { name: "Retry loading older gaps" });
      await expect(retry).toBeFocused({ timeout: 15_000 });
      await shoot(page, retry, `open-gaps-error-${width}-${theme}`);
    });

    test(`run targets failed page ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { targets: manyTargets(260) });
      await page.route("**/api/v1/admin/runs/412?*", (route) => route.fulfill({ status: 503, json: problem(503, "req_7f3a91c2") }));
      await open(page, width, height, theme);
      await page.getByRole("button", { name: "Shopify stores: open runs" }).locator("visible=true").click();
      const drawer = page.getByRole("dialog", { name: "Shopify stores" });
      await drawer.getByRole("button", { name: "Load more targets" }).focus();
      await page.keyboard.press("Enter");
      const retry = drawer.getByRole("button", { name: "Retry loading targets" });
      await expect(retry).toBeFocused({ timeout: 15_000 });
      await shoot(page, retry, `run-targets-error-${width}-${theme}`);
    });

    test(`api down ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { down: true });
      await open(page, width, height, theme);
      const error = page.getByRole("heading", { level: 2, name: "Can't reach the API" });
      await expect(error).toBeVisible({ timeout: 15_000 });
      await shoot(page, error, `api-down-${width}-${theme}`);
    });

    test(`sources retry deadline ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await open(page, width, height, theme);
      const deadline = page.getByText("Retry after Oct 22, 15:00 UTC (in 1h)").locator("visible=true");
      await expect(deadline).toBeVisible();
      await shoot(page, deadline, `sources-deadline-${width}-${theme}`);
    });
  }
}
