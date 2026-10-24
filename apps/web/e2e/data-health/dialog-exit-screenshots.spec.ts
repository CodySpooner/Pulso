import { expect, test } from "@playwright/test";

import { activity, healthySources, mockAdminApi } from "./fixtures";

// imp-165 + imp-166 owner review screenshots, from fixtures only: 1440px and 375px, dark and light.
// - attention-*: CJ's activity expired with every other source healthy, so the panel note and the nav badge
//   count 1 (DEC-223) and the CJ row says why under its Healthy pill.
// - exit-*: the Disable dialog halfway through its exit after Cancel, held there, with its title and body.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/dialog-exit`; output goes to docs/screenshots/imp-165/.
const OUT = "../../docs/screenshots/imp-165";
const expired = healthySources.map((s) => (s.key === "cj" ? { ...s, activity: activity("expired", -3) } : s));
const quiet = { open_gaps: [], latest_gap_ends: {} };

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.beforeEach(async ({ page }) => {
        await mockAdminApi(page, { sources: expired, host: quiet });
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        await expect(page.getByRole("button", { name: "Expired · −3 days" }).locator("visible=true")).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
      });

      test("attention", async ({ page }) => {
        const why = page.getByRole("button", { name: "Expired · −3 days" }).locator("visible=true");
        await why.scrollIntoViewIfNeeded();
        // The badge: on the sidebar's Data Health item at 1440 (below the sidebar's fold), on the tab bar's More at 375.
        const badge = page.getByTestId("data-health-badge").locator("visible=true");
        await badge.scrollIntoViewIfNeeded();
        await expect(badge).toHaveText("1");
        await page.screenshot({ path: `${OUT}/attention-${width}-${theme}.png` });
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      });

      test.describe(() => {
        test.use({ reducedMotion: "no-preference" }); // the exit animation is what this shows
        test("exit", async ({ page }) => {
          await page.getByRole("switch", { name: "CJ Dropshipping enabled" }).locator("visible=true").click();
          const dialog = page.getByRole("dialog", { name: "Disable CJ Dropshipping?" });
          await expect(dialog).toBeVisible();
          await page.waitForTimeout(300); // the enter animation has finished
          // Press Cancel, then hold every animation 60 ms into the exit (of ~120 ms, imp-177).
          await page.evaluate(async () => {
            const cancel = [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find((b) => b.textContent === "Cancel")!;
            cancel.click();
            while (!document.querySelector('[role="dialog"][data-state="closed"]')) await new Promise(requestAnimationFrame);
            for (const a of document.getAnimations()) {
              a.pause();
              a.currentTime = 60;
            }
          });
          await expect(dialog).toHaveAttribute("data-state", "closed");
          await page.screenshot({ path: `${OUT}/exit-${width}-${theme}.png` });
        });
      });
    });
  }
}
