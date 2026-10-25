import { expect, test } from "@playwright/test";

import { contrastMisses, focusStop, SCREENS, type FocusStop } from "./screens";

// p2-39 (Phase 2 end): the AGENTS.md §8 checklist lines a browser can measure, on every Phase 2 screen loaded from
// fixtures. No sideways page scroll at 375px; every keyboard stop in the screen shows its focus ring; every visible
// text run clears WCAG AA against what it is painted on, in dark and light. docs/reports/p2-39.md holds the rest.
const MAX_STOPS = 80;

for (const screen of SCREENS) {
  test.describe(screen.name, () => {
    test("no horizontal page scroll at 375px", async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await screen.open(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    });

    test("every keyboard stop shows a focus ring", async ({ page }) => {
      await screen.open(page);
      const stops: FocusStop[] = [];
      for (let i = 0; i < MAX_STOPS; i++) {
        await page.keyboard.press("Tab");
        const stop = await page.evaluate(focusStop, screen.scope);
        if (stop) stops.push(stop);
      }
      expect(stops.length, "no keyboard stop inside the screen").toBeGreaterThan(0);
      expect(stops.filter((s) => !s.ring || !s.visible)).toEqual([]);
    });

    for (const theme of ["dark", "light"] as const)
      test(`text clears AA contrast (${theme})`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await screen.open(page);
        await page.waitForTimeout(300); // theme transition and fades settle
        expect(await page.evaluate(contrastMisses, screen.scope)).toEqual([]);
      });
  });
}
