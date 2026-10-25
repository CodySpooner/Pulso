import { expect, test, type Page } from "@playwright/test";

import { BOARD, mockBoardsApi, OPEN_TEST, PRODUCT } from "./fixtures";

// WF-3b Boards against fixture responses (the E2E auth bypass, never a database restore).
const Q4 = `/boards/${BOARD(1)}`;
const toast = (page: Page) => page.getByRole("status").filter({ hasText: /\S/ }).last();
const order = (page: Page) => page.getByRole("list", { name: /in your order/ }).getByRole("article").evaluateAll((cards) => cards.map((c) => c.getAttribute("aria-label")));
const noHorizontalScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("create a board inline, rename it, archive it and find it under Archived", async ({ page }) => {
  const api = await mockBoardsApi(page);
  await page.goto("/boards");
  await expect(page.getByRole("link", { name: /Q4 gift ideas/ })).toBeVisible();

  await page.getByRole("button", { name: "New board" }).click();
  await page.getByRole("textbox", { name: "Board name" }).fill("Pet niche");
  await page.keyboard.press("Enter");
  await expect(page.locator("#new-board-error")).toHaveText("You already have a board named “Pet niche”. Archived boards count too.");
  await page.getByRole("textbox", { name: "Board name" }).fill("Desk setups");
  await page.keyboard.press("Enter");
  const tile = page.getByRole("link", { name: /Desk setups/ });
  await expect(tile).toBeFocused(); // first tile, newest activity first; Enter opens it
  await expect(tile).toContainText("0 products");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Desk setups" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No products on this board yet" })).toBeVisible();

  await page.getByRole("button", { name: "Rename board" }).click();
  await page.getByRole("textbox", { name: "Board name" }).fill("Desk setup ideas");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Desk setup ideas" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Rename board" })).toBeFocused();
  await page.getByRole("button", { name: /Add a description/ }).click();
  await page.getByRole("textbox", { name: "Description" }).fill("Monitor lights and cable trays");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: /Monitor lights and cable trays/ })).toBeVisible();
  expect(api.writes().map((c) => c.body)).toEqual([{ name: "Pet niche" }, { name: "Desk setups" }, { name: "Desk setup ideas" }, { description: "Monitor lights and cable trays" }]);

  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(toast(page)).toContainText("Archived Desk setup ideas.");
  await expect(page.getByText(/hidden from your boards/)).toBeVisible();
  await page.getByRole("link", { name: "Boards", exact: true }).first().click();
  await expect(page.getByRole("link", { name: /Q4 gift ideas/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Desk setup ideas/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Archived" }).click();
  await expect(page).toHaveURL(/\?archived=1$/);
  await expect(page.getByRole("link", { name: /Desk setup ideas/ })).toContainText("Archived just now");
  await expect(page.getByRole("link", { name: /Summer 2026/ })).toBeVisible();
});

test("two cards swap places with the keyboard only, and the order persists", async ({ page }) => {
  const api = await mockBoardsApi(page);
  await page.goto(Q4);
  await expect.poll(() => order(page)).toEqual(["Sunset projection lamp", "Galaxy star projector", "Mini waffle maker", "Cloud pillow slides", "Posture corrector brace"]);
  await page.getByRole("button", { name: "Reorder Sunset projection lamp" }).focus(); // from here on, keys only
  await page.keyboard.press("Space");
  await expect(page.locator("#DndLiveRegion-0")).toContainText("Picked up Sunset projection lamp, position 1 of 5.");
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#DndLiveRegion-0")).toContainText("Sunset projection lamp is at position 2 of 5.");
  await page.keyboard.press("Space");
  await expect(page.locator("#DndLiveRegion-0")).toContainText("Dropped Sunset projection lamp at position 2 of 5.");
  await expect.poll(() => order(page)).toEqual(["Galaxy star projector", "Sunset projection lamp", "Mini waffle maker", "Cloud pillow slides", "Posture corrector brace"]);
  expect(api.writes().map((c) => [c.path, c.body])).toEqual([[`/v1/boards/${BOARD(1)}/items/${PRODUCT(1)}`, { position: 1 }]]);
  await expect(page.getByRole("button", { name: "Reorder Sunset projection lamp" })).toBeFocused();

  await page.reload();
  await expect.poll(() => order(page)).toEqual(["Galaxy star projector", "Sunset projection lamp", "Mini waffle maker", "Cloud pillow slides", "Posture corrector brace"]);
});

test("a move by the card menu that fails puts the order back and says so", async ({ page }) => {
  await mockBoardsApi(page, { failMoves: true });
  await page.goto(Q4);
  await page.getByRole("button", { name: "More for Posture corrector brace" }).click();
  await page.getByRole("menuitem", { name: "Move to top" }).click();
  await expect(toast(page)).toContainText("Couldn't save the order: The API is restarting. Try again. Reverted.");
  await expect.poll(async () => (await order(page)).at(-1)).toBe("Posture corrector brace");
});

test("a note autosaves; a failed save keeps the text and Retry saves it", async ({ page }) => {
  const api = await mockBoardsApi(page);
  await page.goto(Q4);
  const note = page.getByRole("textbox", { name: "Note on Galaxy star projector" });
  await note.fill("Test at $24.99 with a 2-pack");
  await expect(page.getByText("Note saved")).toBeVisible();
  expect(api.writes(/items/).map((c) => c.body)).toEqual([{ note: "Test at $24.99 with a 2-pack" }]);

  api.set({ failNotes: true });
  await note.fill("Test at $24.99 with a 2-pack, and a 3-pack at $34.99");
  const card = page.getByRole("article", { name: "Galaxy star projector" });
  await expect(card).toContainText("Couldn't save the note.");
  await expect(note).toHaveValue("Test at $24.99 with a 2-pack, and a 3-pack at $34.99");
  await expect(note).toHaveAttribute("aria-invalid", "true");
  api.set({ failNotes: false });
  await card.getByRole("button", { name: "Retry" }).click();
  await expect(card).toContainText("Note saved");
  expect(api.writes(/items/).at(-1)!.body).toEqual({ note: "Test at $24.99 with a 2-pack, and a 3-pack at $34.99" });

  await page.reload();
  await expect(page.getByRole("textbox", { name: "Note on Galaxy star projector" })).toHaveValue("Test at $24.99 with a 2-pack, and a 3-pack at $34.99");
});

test("Shift-click selects a range; Send to Testing reports what it skipped; Remove has Undo", async ({ page }) => {
  const api = await mockBoardsApi(page);
  await page.goto(Q4);
  await page.getByRole("checkbox", { name: "Select Mini waffle maker" }).check();
  await page.getByRole("checkbox", { name: "Select Posture corrector brace" }).click({ modifiers: ["Shift"] });
  const bar = page.getByRole("toolbar", { name: "Selected products" });
  await expect(bar).toContainText("3 selected");

  await bar.getByRole("button", { name: "Send to Testing" }).click();
  await expect(toast(page)).toContainText("Sent 2 products to Testing as ideas. Already testing: Posture corrector brace.");
  await expect(toast(page).getByRole("link", { name: "Open Testing" })).toHaveAttribute("href", "/testing");
  expect(api.writes(/send-to-testing/)[0].body).toEqual({ product_ids: [PRODUCT(5), PRODUCT(6), OPEN_TEST] });
  await expect(bar).toBeHidden();

  await page.getByRole("checkbox", { name: "Select Galaxy star projector" }).check();
  await page.keyboard.press("Control+a"); // focus is on a checkbox, not typing: selects every card
  await expect(bar).toContainText("5 selected");
  await page.keyboard.press("Escape");
  await expect(bar).toBeHidden();
  await page.getByRole("checkbox", { name: "Select Galaxy star projector" }).check();
  await page.getByRole("checkbox", { name: "Select Mini waffle maker" }).check();
  await bar.getByRole("button", { name: "Remove" }).click();
  await expect(toast(page)).toContainText("Removed 2 products from Q4 gift ideas.");
  await expect.poll(() => order(page)).toEqual(["Sunset projection lamp", "Cloud pillow slides", "Posture corrector brace"]);
  await expect(page.getByText("3 products")).toBeVisible();

  await toast(page).getByRole("button", { name: "Undo" }).click(); // back in place, note and all
  await expect.poll(() => order(page)).toEqual(["Sunset projection lamp", "Galaxy star projector", "Mini waffle maker", "Cloud pillow slides", "Posture corrector brace"]);
  await expect(page.getByRole("textbox", { name: "Note on Mini waffle maker" })).toHaveValue("Holiday breakfast angle.");
});

test("the table view shows the same cards in order and moves them by menu", async ({ page }) => {
  const api = await mockBoardsApi(page);
  await page.goto(Q4);
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await expect(page).toHaveURL(/\?view=table$/);
  const rows = page.getByRole("table", { name: /in your order/ }).getByRole("rowheader");
  await expect(rows).toHaveText(["Sunset projection lamp", "Galaxy star projector", "Mini waffle maker", "Cloud pillow slides", "Posture corrector brace"]);
  await page.getByRole("button", { name: "More for Sunset projection lamp" }).click();
  await page.getByRole("menuitem", { name: "Move down" }).click();
  await expect(rows).toHaveText(["Galaxy star projector", "Sunset projection lamp", "Mini waffle maker", "Cloud pillow slides", "Posture corrector brace"]);
  expect(api.writes().at(-1)!.body).toEqual({ position: 1 });
  await expect(page.getByRole("textbox", { name: "Note on Sunset projection lamp" })).toHaveValue(/sunset vibes/);
  await page.reload();
  await expect(page.getByRole("button", { name: "Table", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("loading, empty, error, stale and no-image states", async ({ page }) => {
  await mockBoardsApi(page, { hold: true });
  await page.goto("/boards");
  await expect(page.getByRole("status", { name: "Loading your boards" })).toBeVisible();
  await page.unrouteAll({ behavior: "ignoreErrors" });

  await mockBoardsApi(page, { status: 503 });
  await page.goto("/boards");
  await expect(page.getByRole("heading", { name: "Couldn't load your boards" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.unrouteAll({ behavior: "ignoreErrors" });

  await mockBoardsApi(page, { boards: [], items: {} });
  await page.goto("/boards");
  await expect(page.getByRole("heading", { name: "Create a board to collect ideas" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Board name" })).toBeVisible(); // create without a click first
  await page.getByRole("button", { name: "Archived" }).click();
  await expect(page.getByRole("heading", { name: "No archived boards" })).toBeVisible();
  await page.unrouteAll({ behavior: "ignoreErrors" });

  const api = await mockBoardsApi(page);
  await page.goto(Q4);
  const bundle = page.getByRole("article", { name: "Posture corrector brace" });
  await expect(bundle).toContainText("No image yet");
  api.set({ itemsStatus: 503 });
  await page.getByRole("button", { name: "More for Sunset projection lamp" }).click();
  await page.getByRole("menuitem", { name: "Move down" }).click(); // the move saves; the refetch after it fails
  await expect(page.getByRole("group", { name: "Couldn't refresh this board" })).toContainText("Showing data as of");
  await expect(page.getByRole("article", { name: "Sunset projection lamp" })).toBeVisible();

  await page.goto(`/boards/${BOARD(99)}`);
  await expect(page.getByRole("heading", { name: "Board not found" })).toBeVisible();
});

test("phone width: no horizontal page scroll on the index, the grid or the table", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockBoardsApi(page);
  await page.goto("/boards");
  await expect(page.getByRole("link", { name: /Q4 gift ideas/ })).toBeVisible();
  expect(await noHorizontalScroll(page)).toBe(true);
  await page.goto(Q4);
  await expect(page.getByRole("article", { name: "Sunset projection lamp" })).toBeVisible();
  expect(await noHorizontalScroll(page)).toBe(true);
  await page.goto(`${Q4}?view=table`);
  await expect(page.getByRole("rowheader", { name: "Sunset projection lamp" })).toBeVisible();
  expect(await noHorizontalScroll(page)).toBe(true);
});
