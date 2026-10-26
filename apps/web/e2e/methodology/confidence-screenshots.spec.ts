import { expect, test } from "@playwright/test";

// p4-35 (MT-1 part 2, DEC-354) owner review screenshots of /methodology#confidence and the explanation contract's new
// freshness fields, rendered from the committed export (no data, no API) under the E2E auth bypass: 1440px and 375px,
// dark and light. Run with `pnpm --filter web e2e:screenshots e2e/methodology/confidence`; output: docs/screenshots/p4-35/.
const OUT = "../../docs/screenshots/p4-35";

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

      for (const [name, section, table] of [
        ["confidence", "confidence", "Source cadences"],
        ["cadence", "confidence", "Source cadences"], // 375px only: the table sits below the rule there
        ["component-fields", "explanation", "Component fields"],
      ] as const)
        test(name, async ({ page }) => {
          test.skip(name === "cadence" && width === 1440, "the confidence shot shows the table at 1440px");
          await page.goto(`/methodology#${section}`);
          await expect(page.locator(`#${section}`)).toBeVisible();
          const rows = page.getByRole("table", { name: table });
          if (name === "component-fields") await rows.getByRole("row", { name: /^freshness/ }).first().scrollIntoViewIfNeeded();
          else if (name === "cadence") await rows.scrollIntoViewIfNeeded();
          else await page.locator(`#${section}-title`).scrollIntoViewIfNeeded();
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
          await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
        });
    });
  }
}
