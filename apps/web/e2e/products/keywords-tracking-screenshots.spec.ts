import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { decided, mockKeywordsApi, setFull, trackingOff, undecided, type KeywordsMock } from "./keywords-fixtures";

// p3-06 (KW-2) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Search keywords
// section with the SerpApi cost line and the Tracked markers: room in the weekly set, the set full, tracking off, and
// keyboard focus on a Confirm (the cost is its description). The whole Trends tab once at 1440.
// Run with `pnpm --filter web e2e:screenshots e2e/products/keywords-tracking`; output: docs/screenshots/p3-06/.
const OUT = "../../docs/screenshots/p3-06";
const URL = `/products/${PRODUCT_ID}?tab=trends`;
const section = (page: Page) => page.getByRole("region", { name: "Search keywords" });

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 1000],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ hasTouch: width === 375 });
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
        await mockProductApi(page);
      });

      const open = async (page: Page, options: KeywordsMock) => {
        await mockKeywordsApi(page, options);
        await page.goto(URL);
        await expect(section(page).getByRole("list", { name: "Suggested keywords" })).toBeVisible();
      };
      const shot = async (page: Page, name: string, full = false) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(400);
        const path = `${OUT}/${name}-${width}-${theme}.png`;
        // Phones scroll the document; from 1024px the page scrolls inside <main>, so grow the viewport instead.
        if (width < 1024) return page.screenshot({ path, fullPage: true });
        if (!full) return section(page).screenshot({ path });
        const contentHeight = await page.evaluate(() => document.getElementById("main")!.scrollHeight + 80);
        await page.setViewportSize({ width, height: Math.max(height, contentHeight) });
        await page.waitForTimeout(500);
        await page.screenshot({ path });
      };

      test("tracked", async ({ page }) => {
        await open(page, { body: decided });
        await expect(section(page).getByText("12 of 50 weekly slots used.")).toBeVisible();
        await shot(page, "tracked");
        if (width > 1024) await shot(page, "trends-tab", true);
      });

      test("set full", async ({ page }) => {
        await open(page, { body: setFull });
        await expect(section(page).getByRole("img", { name: "Not tracked: weekly set full" })).toBeVisible();
        await shot(page, "set-full");
      });

      test("tracking off", async ({ page }) => {
        await open(page, { body: trackingOff });
        await expect(section(page).getByText("Trends tracking is off.")).toBeVisible();
        await shot(page, "tracking-off");
      });

      test("keyboard focus", async ({ page }) => {
        await open(page, { body: undecided });
        await section(page).getByRole("textbox", { name: "Add a keyword" }).focus();
        await page.keyboard.press("Tab"); // Add
        await page.keyboard.press("Tab"); // the first Confirm, described by the cost line
        await expect(section(page).getByRole("button", { name: "Confirm sunset projection lamp" })).toBeFocused();
        await shot(page, "focus");
      });
    });
  }
}
