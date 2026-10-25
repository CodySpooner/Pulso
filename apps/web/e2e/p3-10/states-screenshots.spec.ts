import { test } from "@playwright/test";

import { STATES } from "./states";

// p3-10 (Phase 3 Q-2) owner review screenshots, from fixtures only: 1440px and 375px, dark and light, of each state
// this task fixes. Run with `pnpm --filter web e2e:screenshots e2e/p3-10`; output: docs/screenshots/p3-10/.
const OUT = "../../docs/screenshots/p3-10";

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

      for (const state of STATES)
        test(state.name, async ({ page }) => {
          await state.setup(page);
          await page.goto(state.url);
          await state.ready(page);
          await page.evaluate(() => document.fonts.ready);
          if (state.focus) await state.focus(page).evaluate((el) => el.scrollIntoView({ block: "center" }));
          await page.waitForTimeout(300);
          await page.screenshot({ path: `${OUT}/${state.name}-${width}-${theme}.png` });
        });
    });
  }
}
