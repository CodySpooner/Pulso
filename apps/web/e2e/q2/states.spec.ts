import { expect, test } from "@playwright/test";

import { STATES } from "./states";

// p2-30 (Q-2): every Phase 2 view × state cell that no earlier spec proved, at desktop and phone width (states.ts).
for (const [width, height] of [
  [1440, 900],
  [375, 812],
]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height }, hasTouch: width === 375 });

    for (const state of STATES)
      test(state.name, async ({ page }) => {
        await state.setup(page);
        await page.goto(state.url);
        await state.ready(page);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width); // never sideways
      });
  });
}
