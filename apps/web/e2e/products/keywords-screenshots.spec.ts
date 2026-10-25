import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { decided, empty, mockKeywordsApi, type KeywordsMock } from "./keywords-fixtures";

// p3-02 (KW-1) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Trends tab with
// keywords decided (whole page), then the section (the whole page on phones): rejected open, keyboard focus, loading,
// error, empty, a failed save, stale.
// Run with `pnpm --filter web e2e:screenshots e2e/products/keywords-screenshots`; output: docs/screenshots/p3-02/.
const OUT = "../../docs/screenshots/p3-02";
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

      const open = async (page: Page, options: KeywordsMock = {}) => {
        await mockKeywordsApi(page, options);
        await page.goto(URL);
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

      test("decided", async ({ page }) => {
        await open(page, { body: decided });
        await expect(page.getByTestId("trends-canvas")).toBeVisible();
        await expect(section(page).getByRole("list", { name: "Confirmed keywords" })).toBeVisible();
        await shot(page, "decided");
        await shot(page, "trends-tab", true);
      });

      test("rejected open", async ({ page }) => {
        await open(page, { body: decided });
        await section(page).getByText("Rejected (1)").click();
        await expect(section(page).getByRole("button", { name: "Confirm usb instead" })).toBeVisible();
        await shot(page, "rejected-open");
      });

      test("keyboard focus", async ({ page }) => {
        await open(page);
        await section(page).getByRole("button", { name: "Confirm sunset projection lamp" }).focus();
        await page.keyboard.press("Enter");
        await expect(section(page).getByRole("button", { name: "Confirm lamp" })).toBeFocused();
        await shot(page, "focus");
      });

      test("loading", async ({ page }) => {
        await open(page, { hold: true });
        await expect(section(page).getByLabel("Loading keywords")).toBeVisible();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await open(page, { status: 503 });
        await expect(section(page).getByRole("heading", { name: "Couldn't load keywords" })).toBeVisible();
        await shot(page, "error");
      });

      test("empty", async ({ page }) => {
        await open(page, { body: empty });
        await expect(section(page).getByText("No usable phrase", { exact: false })).toBeVisible();
        await shot(page, "empty");
      });

      test("stale", async ({ page }) => {
        await open(page, { body: decided, failSaves: true, refetchStatus: 503 });
        await section(page).getByRole("button", { name: "Confirm lamp" }).click();
        await expect(section(page).getByRole("group", { name: "Couldn't refresh keywords" })).toBeVisible();
        await shot(page, "stale");
      });

      test("save failed", async ({ page }) => {
        await open(page, { body: decided, failSaves: true });
        await section(page).getByRole("button", { name: "Confirm lamp" }).click();
        await expect(section(page).getByRole("alert")).toBeVisible();
        await shot(page, "save-failed");
      });
    });
  }
}
