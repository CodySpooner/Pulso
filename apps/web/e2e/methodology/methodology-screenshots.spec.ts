import { expect, test, type Page } from "@playwright/test";

// p4-06 (MT-1) owner review screenshots of /methodology, rendered from the committed export (no data, no API) under
// the E2E auth bypass: 1440px and 375px, dark and light; the top, the thresholds, the scores not built yet, the
// contract and confidence. Run with `pnpm --filter web e2e:screenshots e2e/methodology`; output: docs/screenshots/p4-06/.
const OUT = "../../docs/screenshots/p4-06";

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

      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      for (const [name, hash, section] of [
        ["methodology", "", "lifecycle-stage"],
        ["thresholds", "#lifecycle-stage-title", "lifecycle-stage"],
        ["not-built", "#trend-score", "trend-score"],
        ["contract", "#explanation", "explanation"],
        ["confidence", "#confidence", "confidence"],
      ] as const)
        test(name, async ({ page }) => {
          await page.goto(`/methodology${hash}`);
          await expect(page.locator(`#${section}`)).toBeVisible();
          if (name === "thresholds") await page.getByRole("table", { name: "Lifecycle Stage thresholds" }).scrollIntoViewIfNeeded();
          // The row anchor lands under the card's header; bring the header back so the shot shows both.
          if (name === "not-built") await page.locator("#not-built-title").scrollIntoViewIfNeeded();
          await shot(page, name);
        });
    });
  }
}
