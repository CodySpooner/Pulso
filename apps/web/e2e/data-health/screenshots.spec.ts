import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// P1-12 owner review screenshots from fixtures only: 1440px and 375px, dark and light, plus the run drawer.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health`; output goes to docs/screenshots/P1-12/.
const OUT = "../../docs/screenshots/P1-12";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`data health ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
      await expect(page.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(500);
      // From 1024px the page scrolls inside <main>, so fullPage can't see it: grow the viewport instead.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/data-health-${width}-${theme}.png`, fullPage: width < 1024 });
    });

    test(`run drawer ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await page.getByRole("button", { name: "Shopify stores: open runs" }).first().click();
      await expect(page.getByRole("dialog", { name: "Shopify stores" })).toContainText("#9001");
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/run-drawer-${width}-${theme}.png` });
    });

    // imp-057 / imp-090: the API-down page, its error an h2 under the page h1 set like the panel titles (title-3,
    // 600). Output goes to docs/screenshots/imp-090/ (imp-057/ keeps the before shots).
    test(`api down ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { down: true });
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");
      await expect(page.getByRole("heading", { level: 2, name: "Can't reach the API" })).toBeVisible({ timeout: 15_000 });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(500);
      await page.screenshot({ path: `../../docs/screenshots/imp-090/api-down-${width}-${theme}.png` });
    });
  }
}
