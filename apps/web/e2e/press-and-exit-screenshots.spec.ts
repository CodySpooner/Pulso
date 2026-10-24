import { expect, test } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-177 + imp-141 owner review screenshots, from fixtures only: 1440px and 375px, dark and light.
// - exit-*: the Disable dialog halfway (60 ms) through its 120 ms exit after Cancel, held there.
// - locked-press-*: the locked "Run CJ Dropshipping now" held under a pointer press, at full size, its reason shown.
// Run with `pnpm --filter web e2e:screenshots e2e/press-and-exit`; output goes to docs/screenshots/imp-177/.
const OUT = "../../docs/screenshots/imp-177";

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ reducedMotion: "no-preference" }); // the exit and the press are what this shows
      test.beforeEach(async ({ page }) => {
        await mockAdminApi(page);
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        await expect(page.getByRole("switch", { name: "CJ Dropshipping enabled" }).locator("visible=true")).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
      });

      test("exit", async ({ page }) => {
        await page.getByRole("switch", { name: "CJ Dropshipping enabled" }).locator("visible=true").click();
        const dialog = page.getByRole("dialog", { name: "Disable CJ Dropshipping?" });
        await expect(dialog).toBeVisible();
        await page.waitForTimeout(300); // the enter animation has finished
        // The exit is held from its first frame, so no frame stall can end it before the shot (imp-183).
        await page.addStyleTag({ content: "[data-state=closed] { animation-play-state: paused !important; }" });
        await dialog.getByRole("button", { name: "Cancel" }).evaluate((b: HTMLElement) => b.click());
        await expect(dialog).toHaveAttribute("data-state", "closed");
        await page.evaluate(() => {
          for (const a of document.getAnimations()) {
            a.pause();
            a.currentTime = 60;
          }
        });
        await page.screenshot({ path: `${OUT}/exit-${width}-${theme}.png` });
      });

      test("locked press", async ({ page }) => {
        const run = page.getByRole("button", { name: "Run CJ Dropshipping now" }).locator("visible=true");
        await run.scrollIntoViewIfNeeded();
        const rest = (await run.boundingBox())!;
        await page.mouse.move(rest.x + rest.width / 2, rest.y + rest.height / 2);
        await page.mouse.down();
        await expect(page.getByRole("tooltip")).toContainText("Live collectors run only on the collector host.");
        await page.waitForTimeout(200); // the 120 ms press transition would have finished
        expect((await run.boundingBox())!.width).toBe(rest.width);
        await page.screenshot({ path: `${OUT}/locked-press-${width}-${theme}.png` });
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        await page.mouse.move(0, 0);
        await page.mouse.up();
      });
    });
  }
}
