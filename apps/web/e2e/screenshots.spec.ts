import { expect, test } from "@playwright/test";

// Owner review screenshots of the Phase 0 shell (WEB-6): 1440px and 375px, dark and light.
// Run with `pnpm --filter web e2e:screenshots`; output goes to docs/screenshots/phase-0/.
const OUT = "../../docs/screenshots/phase-0";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`shell ${width}px ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(800); // logo draw (instant under reduced motion) and lazy Motion features
      await page.screenshot({ path: `${OUT}/shell-${width}-${theme}.png` });
    });
  }
}

test("command palette 1440px dark", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  await page.goto("/");
  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/palette-1440-dark.png` });
});

test("coming-soon route 1440px dark", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("theme", "dark"));
  await page.goto("/discover");
  await expect(page.getByText("Discover arrives in Phase 2")).toBeVisible();
  await page.screenshot({ path: `${OUT}/coming-soon-1440-dark.png` });
});
