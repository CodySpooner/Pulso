import { test } from "@playwright/test";

import { STATES } from "./states";

// p2-30 (Q-2) owner review screenshots, from fixtures only: 1440px and 375px, dark and light, of each state cell this
// task proves whose look no earlier task captured. Run with `pnpm --filter web e2e:screenshots e2e/q2`; output:
// docs/screenshots/p2-30/.
const OUT = "../../docs/screenshots/p2-30";

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

      for (const state of STATES.filter((s) => !s.seenIn))
        test(state.name, async ({ page }) => {
          await state.setup(page);
          await page.goto(state.url);
          await state.ready(page);
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          await page.screenshot({ path: `${OUT}/${state.name}-${width}-${theme}.png` });
        });
    });
  }
}
