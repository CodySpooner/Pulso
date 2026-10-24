import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-169 owner review screenshots from fixtures only, 1440px and 375px, dark and light, with GET /host 503: the
// focused "Collector host card" link in the Open gaps line (the page, and a 2x close-up of the line), and Google
// Trends' focused Unknown note, whose arrow box changed. Run with
// `pnpm --filter web e2e:screenshots e2e/data-health/inline-link-ring`; output goes to docs/screenshots/imp-169/.
const OUT = "../../docs/screenshots/imp-169";

async function open(page: Page, width: number, height: number, theme: string) {
  await mockAdminApi(page);
  await page.route(
    (url) => url.pathname === "/api/v1/admin/host",
    (route) => route.fulfill({ status: 503, json: problem(503, "req_host_503") }),
  );
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme as "dark" | "light" });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await page.evaluate(() => document.fonts.ready);
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`focused Open gaps link ${width}px ${theme}`, async ({ page }) => {
      await open(page, width, height, theme);
      const link = page.getByRole("region", { name: "Coverage", exact: true }).getByRole("link", { name: "Collector host card" });
      await link.focus();
      await link.evaluate((el) => el.scrollIntoView({ block: "center" })); // clear of the phone's bottom nav
      await page.waitForTimeout(200);
      await page.screenshot({ path: `${OUT}/link-focused-${width}-${theme}.png` });
    });

    test(`focused Unknown note link ${width}px ${theme}`, async ({ page }) => {
      await open(page, width, height, theme);
      const trigger = page.getByRole("button", { name: "Google Trends: open runs" });
      const trends =
        width < 768 ? page.getByRole("listitem").filter({ has: trigger }) : page.getByRole("region", { name: "Sources table" }).getByRole("row").filter({ has: trigger });
      const link = trends.getByRole("link", { name: /^Gap check didn't load/ });
      await expect(link).toBeVisible();
      await link.focus();
      await link.evaluate((el) => el.scrollIntoView({ block: "center" }));
      await page.waitForTimeout(200);
      await page.screenshot({ path: `${OUT}/unknown-note-focused-${width}-${theme}.png` });
    });
  }
}

test.describe("close-ups", () => {
  test.use({ deviceScaleFactor: 2 });
  for (const theme of ["dark", "light"] as const) {
    for (const [width, height] of [
      [1440, 900],
      [375, 812],
    ]) {
      test(`focused Open gaps link close-up ${width}px ${theme}`, async ({ page }) => {
        await open(page, width, height, theme);
        const link = page.getByRole("region", { name: "Coverage", exact: true }).getByRole("link", { name: "Collector host card" });
        await link.focus();
        await link.evaluate((el) => el.scrollIntoView({ block: "center" }));
        await page.waitForTimeout(200);
        const line = (await link.locator("xpath=..").boundingBox())!; // the Open gaps line
        await page.screenshot({ path: `${OUT}/link-focused-line-${width}-${theme}.png`, clip: { x: line.x - 8, y: line.y - 4, width: line.width + 16, height: line.height + 12 } });
      });
    }
  }
});
