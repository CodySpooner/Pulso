import { expect, test } from "@playwright/test";

// p3-12 (Phase 3 end) owner review screenshots of the coming-soon page once CURRENT_PHASE is 4, from the E2E auth
// bypass (no data): 1440px and 375px, dark and light. Run with `pnpm --filter web e2e:screenshots e2e/p3-12`;
// output: docs/screenshots/p3-12/.
const OUT = "../../docs/screenshots/p3-12";

const PAGES = [
  ["coming-soon-phase-4", "/screener", "Screener arrives in Phase 4"],
  ["coming-soon-later", "/ask", "Ask Pulso arrives in Phase 5"],
] as const;

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

      for (const [name, url, heading] of PAGES)
        test(name, async ({ page }) => {
          await page.goto(url);
          await expect(page.getByRole("heading", { name: heading })).toBeVisible();
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
        });
    });
  }
}
