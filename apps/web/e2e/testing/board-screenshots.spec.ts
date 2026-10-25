import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { mockTestingApi } from "./fixtures";

// p4-08 (WF-5b) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The board, the test
// drawer (with and without a complete start snapshot), the kill-reason dialog, loading, empty, error, stale, and the
// Product Page's Start a test. Run with `pnpm --filter web e2e:screenshots e2e/testing/board-screenshots`;
// output: docs/screenshots/p4-08/.
const OUT = "../../docs/screenshots/p4-08";
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
      });

      const shot = async (page: Page, name: string, fullPage = true) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
      };

      test("board", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing");
        await expect(card(page, "Sunset projection lamp")).toBeVisible();
        await shot(page, "board");
      });

      test("drawer", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing?test=5");
        await expect(page.getByRole("dialog", { name: "Posture corrector brace" })).toContainText("Break-even CPA");
        await shot(page, "drawer", false);
      });

      test("drawer, no break-even yet", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing?test=4");
        await expect(page.getByRole("dialog")).toContainText("Set price and supplier to compute break-even.");
        await shot(page, "drawer-no-source", false);
      });

      test("kill reason", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing");
        await card(page, "Posture corrector brace").getByRole("button", { name: /^Move/ }).click();
        await page.getByRole("menuitem", { name: "Killed…" }).click();
        await expect(page.getByRole("dialog", { name: "Why kill Posture corrector brace?" })).toBeVisible();
        await shot(page, "kill-reason", false);
      });

      test("move menu", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing");
        await card(page, "Sunset projection lamp").getByRole("button", { name: /^Move/ }).click();
        await expect(page.getByRole("menuitem", { name: "Researching" })).toBeVisible();
        await shot(page, "move-menu", false);
      });

      test("loading", async ({ page }) => {
        await mockTestingApi(page, { hold: true });
        await page.goto("/testing");
        await expect(page.getByRole("status", { name: "Loading your tests" })).toBeAttached();
        await page.waitForTimeout(400); // past the skeleton's 150 ms delay
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockTestingApi(page, { items: [] });
        await page.goto("/testing");
        await expect(page.getByRole("heading", { name: "No tests yet. Start one from a product page" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockTestingApi(page, { status: 503 });
        await page.goto("/testing");
        await expect(page.getByRole("heading", { name: "Couldn't load your tests" })).toBeVisible();
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        const api = await mockTestingApi(page);
        await page.goto("/testing");
        await expect(card(page, "Sunset projection lamp")).toBeVisible();
        api.failLists();
        await card(page, "Sunset projection lamp").getByRole("button", { name: /^Move/ }).click();
        await page.getByRole("menuitem", { name: "Researching" }).click();
        await expect(page.getByRole("group", { name: "Couldn't refresh your tests" })).toBeVisible();
        await shot(page, "stale");
      });

      test("start a test", async ({ page }) => {
        await mockProductApi(page);
        await mockTestingApi(page, { items: [] });
        await page.goto(`/products/${PRODUCT_ID}`);
        await page.getByRole("button", { name: "Start a test" }).click();
        await expect(page.getByRole("status").filter({ hasText: "Added to Idea." })).toBeVisible();
        await shot(page, "start-test", false);
      });
    });
  }
}
