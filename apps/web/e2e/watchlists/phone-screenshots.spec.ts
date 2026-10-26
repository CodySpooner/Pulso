import { expect, test, type Page } from "@playwright/test";

import { CATALOG, mockWatchlistsApi } from "./fixtures";

// p4-38 (WF-8) owner review screenshots, from fixtures only: /watchlists at 1440px and 375px, dark and light. The list,
// a row's menu (its Move to inline on a phone) and the undo toast, on a notched phone at 375px. Run with
// `pnpm --filter web e2e:screenshots e2e/watchlists/phone-screenshots`; output: docs/screenshots/p4-38/.
const OUT = "../../docs/screenshots/p4-38";
const insets = { top: 47, bottom: 34 }; // iPhone 14 portrait

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
        if (width === 375) await (await page.context().newCDPSession(page)).send("Emulation.setSafeAreaInsetsOverride", { insets });
        await mockWatchlistsApi(page);
        await page.goto("/watchlists");
        await expect(page.getByRole("link", { name: CATALOG[0].title, exact: true }).locator("visible=true")).toBeVisible();
      });

      const shot = async (page: Page, name: string, fullPage = true) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);
        await page.screenshot({ path: `${OUT}/watchlists-${name}-${width}-${theme}.png`, fullPage });
      };
      const actions = (page: Page) => page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).locator("visible=true");

      test("list", async ({ page }) => {
        await shot(page, "list");
      });

      test("row menu", async ({ page }) => {
        await actions(page).click();
        await expect(page.getByRole("menuitem", { name: "Remove" })).toBeVisible();
        await shot(page, "row-menu", false);
      });

      test("undo toast", async ({ page }) => {
        await actions(page).click();
        await page.getByRole("menuitem", { name: "Remove" }).click();
        await expect(page.getByRole("link", { name: CATALOG[0].title, exact: true })).toHaveCount(0); // its fade-out is over
        await expect(page.getByRole("status").filter({ has: page.getByRole("button", { name: "Undo" }) }).locator("> div")).toHaveCSS("opacity", "1");
        await shot(page, "undo-toast", false);
      });
    });
  }
}
