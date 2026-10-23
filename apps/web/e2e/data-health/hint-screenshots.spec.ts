import { expect, test } from "@playwright/test";

import { mockAdminApi, suppressedSources } from "./fixtures";

// imp-073 owner review screenshots from fixtures only: a status pill's hint open from the keyboard (1440px,
// focus ring visible) and from a tap (375px), dark and light.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/hint`; output goes to docs/screenshots/imp-073/.
const OUT = "../../docs/screenshots/imp-073";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ hasTouch: width === 375 });

      test(`status hint ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page, { sources: suppressedSources });
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Sources", exact: true });
        await expect(panel).toContainText("Run #419 was still active");
        await page.evaluate(() => document.fonts.ready);
        const name = panel.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true");
        const pill = panel.getByRole("button", { name: "Skipped", exact: true }).locator("visible=true");
        await pill.scrollIntoViewIfNeeded();
        if (width === 375) {
          await pill.tap();
        } else {
          await name.focus();
          await page.keyboard.press("Tab");
          await expect(pill).toBeFocused();
        }
        await expect(page.getByRole("tooltip")).toBeVisible();
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/status-hint-${width}-${theme}.png` });
      });
    });
  }
}
