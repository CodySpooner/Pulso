import { expect, test } from "@playwright/test";

import { host, manyGaps, mockAdminApi } from "./fixtures";

// imp-076 owner review screenshots from fixtures only: one open gap ("1 missed slot", "1 range") and nine ranges
// (imp-075's "Show 1 older range"), at 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/plural`; output goes to docs/screenshots/imp-076/.
const OUT = "../../docs/screenshots/imp-076";

for (const [name, gaps, older] of [
  ["one-gap", [host.open_gaps[2]], null],
  ["one-older-range", manyGaps(9), "Show 1 older range"],
] as const) {
  for (const theme of ["dark", "light"] as const) {
    for (const [width, height] of [
      [1440, 900],
      [375, 812],
    ]) {
      test(`${name} ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page, { host: { open_gaps: [...gaps] } });
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        await expect(page.getByRole("region", { name: "Collector host" })).toContainText(gaps.length === 1 ? "1 missed slot ·" : "9 missed slots ·");
        if (older) await expect(page.getByRole("button", { name: older, exact: true })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        await page.evaluate(() => document.fonts.ready);
        // From 1024px the page scrolls inside <main>, so fullPage can't see it: grow the viewport instead.
        const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
        await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
        await page.waitForTimeout(400);
        await page.screenshot({ path: `${OUT}/data-health-${name}-${width}-${theme}.png`, fullPage: width < 1024 });
      });
    }
  }
}
