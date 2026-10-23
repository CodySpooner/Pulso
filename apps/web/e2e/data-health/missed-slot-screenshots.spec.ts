import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-124 + imp-125 owner review screenshots from fixtures only (now 14:00 UTC, Google Trends missed 10:00–12:00):
// the Sources panel with the missed slot and runs cues, the Google Trends drawer, and where its link lands, at
// 1440px and 375px, dark and light. Run with `pnpm --filter web e2e:screenshots e2e/data-health/missed-slot`;
// output goes to docs/screenshots/imp-124/.
const OUT = "../../docs/screenshots/imp-124";

async function load(page: Page, width: number, height: number, theme: "dark" | "light") {
  await mockAdminApi(page);
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await expect(page.getByRole("link", { name: /^Missed Oct 22/ }).locator("visible=true")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`sources panel ${width}px ${theme}`, async ({ page }) => {
      await load(page, width, height, theme);
      // Grow the viewport to the content so the fixed phone bars don't cover the panel.
      const contentHeight = await page.evaluate(() => Math.max(document.getElementById("main")!.scrollHeight + 80, document.documentElement.scrollHeight));
      await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
      await page.waitForTimeout(400);
      await page.getByRole("region", { name: "Sources", exact: true }).screenshot({ path: `${OUT}/sources-${width}-${theme}.png` });
    });

    test(`google trends drawer ${width}px ${theme}`, async ({ page }) => {
      await load(page, width, height, theme);
      await page.getByRole("button", { name: "Google Trends: open runs" }).locator("visible=true").click();
      await expect(page.getByRole("dialog", { name: "Google Trends" })).toContainText("Succeeded");
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT}/drawer-${width}-${theme}.png` });
    });

    test(`open gaps landing ${width}px ${theme}`, async ({ page }) => {
      await load(page, width, height, theme);
      // Keyboard, so the landing heading shows its focus ring.
      await page.getByRole("link", { name: /^Missed Oct 22/ }).locator("visible=true").focus();
      await page.keyboard.press("Enter");
      await expect(page.locator("#open-gaps")).toBeFocused();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${OUT}/open-gaps-landing-${width}-${theme}.png` });
    });
  }
}
