import { expect, test } from "@playwright/test";

import { activity, mockAdminApi, withActivity } from "./fixtures";

// imp-161 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Sources panel with
// CJ's activity in each state, and the order dialog opened from the row.
// Run with `pnpm --filter web e2e:screenshots e2e/data-health/cj-activity`; output goes to docs/screenshots/imp-161/.
const OUT = "../../docs/screenshots/imp-161";
const states = {
  unknown: { state: "unknown", days_remaining: null, as_of: null, observed_at: null },
  ok: activity("ok", 22),
  warn: activity("warn", 5),
  expired: activity("expired", -3),
} as const;

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    for (const [name, a] of Object.entries(states)) {
      test(`cj activity ${name} ${width}px ${theme}`, async ({ page }) => {
        await mockAdminApi(page, { sources: withActivity(a) });
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await page.goto("/admin/data-health");
        const panel = page.getByRole("region", { name: "Sources", exact: true });
        const edit = panel.getByRole("button", { name: /^(Update|Add order for) CJ activity$/ }).locator("visible=true");
        await expect(edit).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        await panel.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);

        if (name !== "warn") return;
        await edit.click();
        const dialog = page.getByRole("dialog", { name: "Latest CJ order" });
        await dialog.getByLabel("Order date and time (UTC)").fill("2026-10-20T09:30");
        await dialog.getByLabel("Amount").fill("42.50");
        await dialog.getByRole("button", { name: "Save order" }).focus();
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/dialog-${width}-${theme}.png` });
      });
    }
  }
}
