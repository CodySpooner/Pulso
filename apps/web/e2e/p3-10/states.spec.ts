import { expect, test } from "@playwright/test";

import { openPalette } from "../search/fixtures";
import { STATES } from "./states";

// p3-10 (Phase 3 Q-2): every Phase 3 view × state cell this task fixes, at desktop and phone width (states.ts).
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

// DEC-302 (a): the sidebar and the palette say Store Spy has no source, never which phase it arrives in.
test("the sidebar and the palette say Store Spy has no source yet", async ({ page }) => {
  await page.goto("/stores");
  await expect(page.getByRole("link", { name: /^Store Spy\s*, no source yet$/ })).toHaveAttribute("aria-current", "page");
  const input = await openPalette(page);
  await input.fill("store spy");
  await expect(page.getByRole("option", { name: /^Store Spy/ })).toContainText("No source yet");
  await expect(page.getByRole("option", { name: /^Store Spy/ })).not.toContainText("Phase 3");
});
