import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-152 + imp-158 + imp-159 owner review screenshots from fixtures only, 1440px and 375px, dark and light:
// the host card while GET /sources is held after GET /host landed (the latest-gap line keeps its skeleton) and
// once the names land; with GET /host 503, the label-first Open gaps line and the host card's Retry focused by
// its link (Enter, so the focus ring shows). Run with
// `pnpm --filter web e2e:screenshots e2e/data-health/open-gaps-link`; output goes to docs/screenshots/imp-152/.
const OUT = "../../docs/screenshots/imp-152";

async function open(page: Page, width: number, height: number, theme: string) {
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`host before sources ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      let release!: () => void;
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route((url) => url.pathname === "/api/v1/admin/sources", async (route) => {
        await held;
        await route.fallback();
      });
      await open(page, width, height, theme);
      const card = page.getByRole("region", { name: "Collector host" });
      await expect(card.locator("dl")).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await card.screenshot({ path: `${OUT}/host-card-names-pending-${width}-${theme}.png` });
      release();
      await expect(card.getByText(/latest Google Trends/)).toBeVisible();
      await card.screenshot({ path: `${OUT}/host-card-loaded-${width}-${theme}.png` });
    });

    test(`host 503 line and focused Retry ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.route(
        (url) => url.pathname === "/api/v1/admin/host",
        (route) => route.fulfill({ status: 503, json: problem(503, "req_host_503") }),
      );
      await open(page, width, height, theme);
      const panel = page.getByRole("region", { name: "Coverage", exact: true });
      const link = panel.getByRole("link", { name: "Collector host card" });
      await expect(link).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await link.focus();
      await link.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      await page.screenshot({ path: `${OUT}/host-503-line-${width}-${theme}.png` });

      await page.keyboard.press("Enter");
      await expect(page.getByRole("region", { name: "Collector host" }).getByRole("button", { name: "Retry" })).toBeFocused();
      await page.waitForTimeout(200);
      await page.screenshot({ path: `${OUT}/host-503-retry-focused-${width}-${theme}.png` });
    });
  }
}
