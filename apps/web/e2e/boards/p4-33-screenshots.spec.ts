import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi, mockProductApi, product } from "../products/fixtures";
import { BOARD, mockBoardsApi, type BoardsMock } from "./fixtures";

// p4-33 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Add-to-board picker on a
// Discover card and row and on the Product Page (New board, a taken name), its loading, error and no-boards states,
// the Added toast, and the board's Export CSV. Run with `pnpm --filter web e2e:screenshots e2e/boards/p4-33-screenshots`;
// output: docs/screenshots/p4-33/.
const OUT = "../../docs/screenshots/p4-33";
const picker = (page: Page) => page.getByRole("dialog", { name: /to a board$/ });
const cards = (page: Page) => page.getByRole("list", { name: "Products" }).getByRole("article");

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

      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };
      const discover = async (page: Page, options: BoardsMock = {}, view = "") => {
        await mockBoardsApi(page, options);
        await mockFeedApi(page, { items: feedItems(12) });
        await page.goto(`/discover${view}`);
      };
      const openOnCard = async (page: Page) => {
        await cards(page).first().getByRole("link").focus();
        await page.keyboard.press("b");
        await expect(picker(page)).toBeVisible();
        await expect(picker(page).getByRole("combobox")).toBeFocused();
      };

      test("picker on a Discover card", async ({ page }) => {
        await discover(page);
        await openOnCard(page);
        await expect(picker(page).getByRole("option", { name: /Q4 gift ideas/ })).toHaveAttribute("aria-selected", "true");
        await shot(page, "picker-card");
      });

      test("search with New board", async ({ page }) => {
        await discover(page);
        await openOnCard(page);
        await page.keyboard.type("gift");
        await expect(picker(page).getByRole("option", { name: "New board “gift”" })).toBeVisible();
        await shot(page, "picker-search");
      });

      test("added toast", async ({ page }) => {
        await discover(page);
        await openOnCard(page);
        await page.keyboard.press("Enter");
        await expect(page.getByRole("status").filter({ hasText: "Added to Q4 gift ideas" })).toBeVisible();
        await shot(page, "added-toast");
      });

      test("picker on a table row", async ({ page }) => {
        await discover(page, {}, "?view=table");
        await page.getByRole("region", { name: "Products" }).locator("tbody tr").first().getByRole("button", { name: /to a board$/ }).click();
        await expect(picker(page)).toBeVisible();
        await shot(page, "picker-row");
      });

      test("loading, error and no boards", async ({ page }) => {
        const mock = await mockBoardsApi(page, { hold: true });
        await mockFeedApi(page, { items: feedItems(12) });
        await page.goto("/discover");
        await openOnCard(page);
        await shot(page, "picker-loading");
        await page.keyboard.press("Escape");
        mock.set({ hold: false, status: 503 });
        await page.reload();
        await openOnCard(page);
        await expect(picker(page).getByRole("heading", { name: "Couldn't load your boards" })).toBeVisible();
        await shot(page, "picker-error");
        await page.keyboard.press("Escape");
        mock.set({ status: undefined });
        mock.boards.length = 0;
        await page.reload();
        await openOnCard(page);
        await expect(picker(page)).toContainText("No boards yet");
        await shot(page, "picker-empty");
      });

      test("Product Page header, then a taken name", async ({ page }) => {
        await mockBoardsApi(page);
        await mockProductApi(page);
        await page.goto(`/products/${product.id}`);
        await expect(page.getByRole("button", { name: "Add to board" })).toBeVisible();
        await shot(page, "product-header");
        await page.keyboard.press("b");
        await expect(picker(page).getByRole("combobox")).toBeFocused();
        await page.keyboard.type("Summer 2026");
        await page.keyboard.press("Enter");
        await expect(picker(page).getByRole("alert")).toBeVisible();
        await shot(page, "product-taken");
      });

      test("board with Export CSV, and an empty board", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(`/boards/${BOARD(1)}`);
        await expect(page.getByRole("button", { name: "Export CSV" })).toBeVisible();
        await shot(page, "board-export");
        const download = page.waitForEvent("download");
        await page.getByRole("button", { name: "Export CSV" }).click();
        await download;
        await expect(page.getByRole("button", { name: "Downloaded" })).toBeVisible();
        await shot(page, "board-export-done");
        await page.goto(`/boards/${BOARD(4)}`);
        await expect(page.getByRole("heading", { name: "No products on this board yet" })).toBeVisible();
        await shot(page, "board-empty");
      });
    });
  }
}
