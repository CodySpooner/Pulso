import { expect, test, type Page } from "@playwright/test";

import { manyGaps, manyTargets, mockAdminApi, problem } from "./fixtures";

// imp-075 review screenshots from fixtures only: the open-gaps and run-targets Load more footers at 1440px and
// 375px, dark and light, plus a failed page. Run with `pnpm --filter web e2e:screenshots e2e/data-health/load-more`.
const OUT = "../../docs/screenshots/imp-075";

async function open(page: Page, width: number, height: number, theme: string) {
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`open gaps load more ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { gaps: manyGaps(260) });
      await open(page, width, height, theme);
      const panel = page.getByRole("region", { name: "Coverage" });
      const more = panel.getByRole("button", { name: "Load older gaps" });
      await more.scrollIntoViewIfNeeded();
      await more.focus(); // shows the focus ring
      await page.waitForTimeout(300);
      await panel.screenshot({ path: `${OUT}/open-gaps-${width}-${theme}.png` });
    });

    test(`run targets load more ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page, { targets: manyTargets(260) });
      await open(page, width, height, theme);
      await page.getByRole("button", { name: "Shopify stores: open runs" }).first().click();
      const drawer = page.getByRole("dialog", { name: "Shopify stores" });
      await drawer.getByRole("button", { name: "Load more targets" }).click();
      await expect(drawer).toContainText("Showing 250 of 260 targets");
      await drawer.getByText("Showing 250 of 260 targets").scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/run-targets-${width}-${theme}.png` });
    });
  }

  test(`open gaps failed page 1440px ${theme}`, async ({ page }) => {
    await mockAdminApi(page, { gaps: manyGaps(260) });
    await page.route("**/api/v1/admin/host?*", (route) => route.fulfill({ status: 503, json: problem(503, "req_7f3a91c2") }));
    await open(page, 1440, 900, theme);
    const panel = page.getByRole("region", { name: "Coverage" });
    await panel.getByRole("button", { name: "Load older gaps" }).click();
    await expect(panel.getByRole("alert")).toContainText("Couldn't load older gaps.", { timeout: 15_000 });
    const footer = panel.getByRole("alert").locator("..");
    await footer.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await footer.screenshot({ path: `${OUT}/open-gaps-error-1440-${theme}.png` });
  });
}
