import { expect, test, type Page } from "@playwright/test";

import { BOARD, mockBoardsApi } from "./fixtures";

// p4-18 (WF-3b) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The index, a board
// as a grid and as a table, a note that couldn't save, a selection, an archived board, and the loading, empty, error
// and stale states. Run with `pnpm --filter web e2e:screenshots e2e/boards/boards-screenshots`;
// output: docs/screenshots/p4-18/.
const OUT = "../../docs/screenshots/p4-18";
const Q4 = `/boards/${BOARD(1)}`;

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

      test("index", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto("/boards");
        await expect(page.getByRole("link", { name: /Q4 gift ideas/ }).locator("img")).toHaveCount(4);
        await shot(page, "index");
      });

      test("index, new board", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto("/boards");
        await page.getByRole("button", { name: "New board" }).click();
        await page.getByRole("textbox", { name: "Board name" }).fill("Desk setups");
        await shot(page, "new-board", false);
      });

      test("index, empty", async ({ page }) => {
        await mockBoardsApi(page, { boards: [], items: {} });
        await page.goto("/boards");
        await expect(page.getByRole("heading", { name: "Create a board to collect ideas" })).toBeVisible();
        await shot(page, "index-empty");
      });

      test("board, grid", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(Q4);
        await expect(page.getByRole("article", { name: "Sunset projection lamp" })).toBeVisible();
        await shot(page, "board");
      });

      test("board, table", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(`${Q4}?view=table`);
        await expect(page.getByRole("rowheader", { name: "Sunset projection lamp" })).toBeVisible();
        await shot(page, "board-table");
      });

      test("board, selection", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(Q4);
        await page.getByRole("checkbox", { name: "Select Galaxy star projector" }).check();
        await page.getByRole("checkbox", { name: "Select Mini waffle maker" }).check();
        await expect(page.getByRole("toolbar", { name: "Selected products" })).toBeVisible();
        await shot(page, "selection", false);
      });

      test("board, note couldn't save", async ({ page }) => {
        await mockBoardsApi(page, { failNotes: true });
        await page.goto(Q4);
        await page.getByRole("textbox", { name: "Note on Galaxy star projector" }).fill("Test at $24.99 with a 2-pack");
        await expect(page.getByRole("article", { name: "Galaxy star projector" })).toContainText("Couldn't save the note.");
        await page.getByRole("textbox", { name: "Note on Galaxy star projector" }).blur();
        await shot(page, "note-retry", false);
      });

      test("board, archived", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(`/boards/${BOARD(5)}`);
        await expect(page.getByText(/hidden from your boards/)).toBeVisible();
        await shot(page, "archived", false);
      });

      test("board, empty", async ({ page }) => {
        await mockBoardsApi(page);
        await page.goto(`/boards/${BOARD(4)}`);
        await expect(page.getByRole("heading", { name: "No products on this board yet" })).toBeVisible();
        await shot(page, "board-empty", false);
      });

      test("loading", async ({ page }) => {
        await mockBoardsApi(page, { hold: true });
        await page.goto("/boards");
        await expect(page.getByRole("status", { name: "Loading your boards" })).toBeVisible();
        await shot(page, "loading", false);
      });

      test("error", async ({ page }) => {
        await mockBoardsApi(page, { status: 503 });
        await page.goto("/boards");
        await expect(page.getByRole("heading", { name: "Couldn't load your boards" })).toBeVisible();
        await shot(page, "error", false);
      });

      test("stale", async ({ page }) => {
        const api = await mockBoardsApi(page);
        await page.goto(Q4);
        await expect(page.getByRole("article", { name: "Sunset projection lamp" })).toBeVisible();
        api.set({ itemsStatus: 503 });
        await page.getByRole("button", { name: "More for Sunset projection lamp" }).click();
        await page.getByRole("menuitem", { name: "Move down" }).click();
        await expect(page.getByRole("group", { name: "Couldn't refresh this board" })).toBeVisible();
        await page.waitForTimeout(6_500); // the move's toast goes first
        await shot(page, "stale", false);
      });
    });
  }
}
