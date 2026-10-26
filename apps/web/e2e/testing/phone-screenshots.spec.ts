import { expect, test, type Page } from "@playwright/test";

import { mockTestingApi } from "./fixtures";

// p4-38 (WF-8) owner review screenshots, from fixtures only: the Testing Board at 1440px and 375px, dark and light. The
// phone's one column with its picker (also stuck under the top bar), the move menu, the drawer as a full sheet on a
// notched phone, and loading. Run with `pnpm --filter web e2e:screenshots e2e/testing/phone-screenshots`;
// output: docs/screenshots/p4-38/.
const OUT = "../../docs/screenshots/p4-38";
const insets = { top: 47, bottom: 34 }; // iPhone 14 portrait
const card = (page: Page, title: string) => page.getByRole("article", { name: title });

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
        // A notched phone in standalone mode: the top bar, the picker and the sheet clear the notch.
        if (width === 375) await (await page.context().newCDPSession(page)).send("Emulation.setSafeAreaInsetsOverride", { insets });
      });

      const shot = async (page: Page, name: string, fullPage = true) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);
        await page.screenshot({ path: `${OUT}/testing-${name}-${width}-${theme}.png`, fullPage });
      };

      test("board", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing");
        await expect(card(page, "LED strip lights")).toBeVisible();
        await shot(page, "board");
      });

      test("loading", async ({ page }) => {
        await mockTestingApi(page, { hold: true });
        await page.goto("/testing");
        await expect(page.getByRole("status", { name: "Loading your tests" })).toBeAttached();
        await page.waitForTimeout(400); // past the skeleton's 150 ms delay
        await shot(page, "loading");
      });

      test("move menu", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing");
        await card(page, "Heatless curling ribbon").getByRole("button", { name: /^Move/ }).click();
        await expect(page.getByRole("menuitem", { name: "Winner" })).toBeVisible();
        await shot(page, "move-menu", false);
      });

      test("drawer", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing?test=5");
        await expect(page.getByRole("dialog", { name: "Posture corrector brace" })).toContainText("Break-even CPA");
        await shot(page, "drawer", false);
      });

      if (width === 375) {
        test("picker stuck under the top bar", async ({ page }) => {
          await mockTestingApi(page);
          await page.goto("/testing");
          await expect(card(page, "LED strip lights")).toBeVisible();
          await page.evaluate(() => scrollTo(0, 700));
          await shot(page, "sticky-picker", false);
        });

        test("an empty column", async ({ page }) => {
          await mockTestingApi(page);
          await page.goto("/testing");
          await expect(card(page, "LED strip lights")).toBeVisible();
          await page.getByRole("group", { name: "Column" }).getByRole("button", { name: /^Idea/ }).click();
          await card(page, "Sunset projection lamp").getByRole("button", { name: /^Move/ }).click();
          await page.getByRole("menuitem", { name: "Researching" }).click();
          await page.getByRole("group", { name: "Column" }).getByRole("button", { name: /^Idea/ }).click();
          await expect(page.getByText("No tests")).toBeVisible();
          await shot(page, "empty-column", false);
        });
      }
    });
  }
}
