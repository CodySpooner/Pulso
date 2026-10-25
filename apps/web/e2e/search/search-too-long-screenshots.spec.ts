import { expect, test } from "@playwright/test";

import { LONG_URL, mockSearchApi, openPalette } from "./fixtures";

// imp-267 (XR-33) owner review screenshots, from fixtures only: the palette's "too long to search" state for a pasted
// product URL, at 1440px and 375px, dark and light. Run with
// `pnpm --filter web e2e:screenshots e2e/search/search-too-long-screenshots`; output: docs/screenshots/imp-267/.
const OUT = "../../docs/screenshots/imp-267";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`too long ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await mockSearchApi(page);
      const input = await openPalette(page);
      await input.fill(LONG_URL);
      await expect(page.getByRole("option", { name: /Too long to search/ })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(300);
      await page.screenshot({ path: `${OUT}/too-long-${width}-${theme}.png` });
    });
  }
}
