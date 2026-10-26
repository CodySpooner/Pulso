import { expect, test, type Page } from "@playwright/test";

import { contrastMisses } from "../p2-39/screens";
import { feedItems, mockFeedApi, mockProductApi, product } from "../products/fixtures";
import { BOARD, mockBoardsApi, type BoardsMock } from "./fixtures";

// WF-3c Add to board (imp-455, DEC-350) on fixture Discover, Product Page and boards APIs, never a database restore.
const items = feedItems(6);
const cards = (page: Page) => page.getByRole("list", { name: "Products" }).getByRole("article");
const picker = (page: Page) => page.getByRole("dialog", { name: /to a board$/ });
const toast = (page: Page, text: string) => page.getByRole("status").filter({ hasText: text });
const adds = (mock: Awaited<ReturnType<typeof mockBoardsApi>>) => mock.writes(/\/items$/).map((c) => [c.path, c.body]);

async function discover(page: Page, options: BoardsMock = {}) {
  const boards = await mockBoardsApi(page, options);
  await mockFeedApi(page, { items });
  await page.goto("/discover");
  await expect(cards(page)).toHaveCount(6);
  return boards;
}

test("B on a focused Discover card picks a board keyboard-only; again says Already on", async ({ page }) => {
  const boards = await discover(page);
  const card = cards(page).first();
  await card.getByRole("link").focus();
  await page.keyboard.press("b");
  await expect(picker(page)).toBeVisible();
  await expect(picker(page).getByRole("combobox")).toBeFocused();
  // Most recently active first, as the API sorts them; archived boards aren't offered.
  await expect(picker(page).getByRole("option")).toHaveText(["Q4 gift ideas5", "Pet niche3", "Bundles to test1", "Kitchen gadgets0", "New board…"]);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter"); // B, ↓, Enter: three keys from a focused product
  await expect(toast(page, "Added to Pet niche")).toBeVisible();
  await expect(picker(page)).toBeHidden();
  await expect(card.getByRole("button", { name: `Add ${items[0].title} to a board` })).toBeFocused();
  expect(adds(boards)).toEqual([[`/v1/boards/${BOARD(2)}/items`, { product_ids: [items[0].id] }]]);

  // The add made Pet niche the most recent board, so B and Enter now pick it.
  await page.keyboard.press("b");
  await expect(picker(page).getByRole("option").first()).toHaveText("Pet niche4");
  await page.keyboard.press("Enter");
  await expect(toast(page, "Already on Pet niche")).toBeVisible();
  await expect(page.getByRole("link", { name: "Open board" })).toHaveCount(1); // the Added toast has gone
  await expect(page.getByRole("link", { name: "Open board" })).toHaveAttribute("href", `/boards/${BOARD(2)}`);
});

test("the search narrows to names, and a table row's button adds without opening the product", async ({ page }) => {
  const boards = await discover(page);
  await page.getByRole("button", { name: "Table", exact: true }).click();
  const row = page.getByRole("region", { name: "Products" }).locator("tbody tr").nth(1);
  await row.getByRole("button", { name: `Add ${items[1].title} to a board` }).click();
  await expect(picker(page).getByRole("combobox")).toBeFocused();
  await page.keyboard.type("kit");
  await expect(picker(page).getByRole("option")).toHaveText(["Kitchen gadgets0", "New board “kit”"]);
  await picker(page).getByRole("option", { name: /Kitchen gadgets/ }).click();
  await expect(toast(page, "Added to Kitchen gadgets")).toBeVisible();
  await expect(page).toHaveURL(/\/discover\?view=table$/);
  expect(adds(boards)).toEqual([[`/v1/boards/${BOARD(4)}/items`, { product_ids: [items[1].id] }]]);
});

test("on the Product Page, B anywhere opens it, and New board creates a board and adds the product", async ({ page }) => {
  const boards = await mockBoardsApi(page);
  await mockProductApi(page);
  await page.goto(`/products/${product.id}`);
  await expect(page.getByRole("button", { name: "Add to board" })).toBeVisible();
  await page.keyboard.press("b");
  await expect(picker(page).getByRole("combobox")).toBeFocused();
  // An archived board's name is taken too: the API's 409 keeps the name and says why.
  await page.keyboard.type("Summer 2026");
  await page.keyboard.press("Enter");
  const name = picker(page).getByRole("textbox", { name: "New board name" });
  await expect(name).toHaveValue("Summer 2026");
  await expect(picker(page).getByRole("alert")).toHaveText("You already have a board with that name. Archived boards count too.");
  await name.fill("Gift guide");
  await page.keyboard.press("Enter");
  await expect(toast(page, "Added to Gift guide")).toBeVisible();
  const made = boards.boards.find((b) => b.name === "Gift guide")!;
  expect(adds(boards)).toEqual([[`/v1/boards/${made.id}/items`, { product_ids: [product.id] }]]);
  expect(boards.items[made.id].map((c) => c.product_id)).toEqual([product.id]);
  await expect(page.getByRole("button", { name: "Add to board" })).toBeFocused();
});

test("loading, error with Retry, and no boards yet", async ({ page }) => {
  const boards = await discover(page, { hold: true });
  const open = async () => {
    await cards(page).first().getByRole("link").focus();
    await page.keyboard.press("b");
  };
  await open();
  await expect(picker(page).getByRole("progressbar")).toBeVisible(); // cmdk's Loading
  await page.keyboard.press("Escape");

  boards.set({ hold: false, status: 503 });
  await page.reload();
  await open();
  await expect(picker(page).getByRole("heading", { name: "Couldn't load your boards" })).toBeVisible();
  boards.set({ status: undefined });
  boards.boards.length = 0;
  await picker(page).getByRole("button", { name: "Retry" }).click();
  await expect(picker(page)).toContainText("No boards yet. Name your first one above.");
  await expect(picker(page).getByRole("option")).toHaveText(["New board…"]);
  await page.keyboard.press("Enter"); // no name typed: the name field
  await expect(picker(page).getByRole("textbox", { name: "New board name" })).toBeFocused();
});

for (const theme of ["dark", "light"] as const)
  test(`AA contrast in the picker, its error and a taken name, and the toast (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    const boards = await discover(page, { status: 503 });
    await cards(page).first().getByRole("link").focus();
    await page.keyboard.press("b");
    await expect(picker(page).getByRole("heading", { name: "Couldn't load your boards" })).toBeVisible();
    expect(await page.evaluate(contrastMisses, '[role="dialog"]')).toEqual([]);
    boards.set({ status: undefined });
    await picker(page).getByRole("button", { name: "Retry" }).click();
    await expect(picker(page).getByRole("option").first()).toHaveAttribute("aria-selected", "true");
    expect(await page.evaluate(contrastMisses, '[role="dialog"]')).toEqual([]);
    await expect(picker(page).getByRole("combobox")).toBeFocused(); // Retry hands focus back to the search
    await page.keyboard.type("Summer 2026");
    await page.keyboard.press("Enter");
    await expect(picker(page).getByRole("alert")).toBeVisible();
    expect(await page.evaluate(contrastMisses, '[role="dialog"]')).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(cards(page).first().getByRole("button", { name: /to a board$/ })).toBeFocused(); // Esc hands focus back
    await page.keyboard.press("b");
    await expect(picker(page).getByRole("option").first()).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");
    await expect(toast(page, "Added to Q4 gift ideas")).toBeVisible();
    await page.waitForTimeout(300);
    expect(await page.evaluate(contrastMisses, '[role="status"]')).toEqual([]);
  });

test.describe("375px", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });
  test("the picker opens on a card and a table row with no horizontal scroll", async ({ page }) => {
    await discover(page);
    await cards(page).first().getByRole("button", { name: `Add ${items[0].title} to a board` }).tap();
    await expect(picker(page)).toBeVisible();
    const box = (await picker(page).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(375);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Table", exact: true }).tap();
    await page.getByRole("region", { name: "Products" }).locator("tbody tr").first().getByRole("button", { name: /to a board$/ }).tap();
    await expect(picker(page)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
