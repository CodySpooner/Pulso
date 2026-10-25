import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { CATALOG, MAIN, mockWatchlistsApi, PET } from "./fixtures";

// WF-2b Watchlists against fixture responses (the E2E auth bypass, never a database restore).
const toast = (page: Page) => page.getByRole("status").filter({ hasText: /\S/ }).last();
const table = (page: Page, list: string) => page.getByRole("region", { name: `${list} products` });
const row = (page: Page, list: string, title: string) => table(page, list).getByRole("row").filter({ has: page.getByRole("link", { name: title, exact: true }) });
const nav = (page: Page) => page.getByRole("navigation", { name: "Watchlists" });
const deletes = <W extends { method: string }>(writes: W[]) => writes.filter((w) => w.method === "DELETE");

test("star from Discover by keyboard, then find it on Main", async ({ page }) => {
  const { writes } = await mockWatchlistsApi(page, { store: { lists: [], items: [] } });
  await page.goto("/discover?view=table");
  const title = CATALOG[2].title;
  const star = page.getByRole("button", { name: `Watch ${title}` });
  await expect(star).toHaveAttribute("aria-pressed", "false");
  await star.focus(); // from here on, keys only
  await page.keyboard.press("Enter");
  await expect(star).toHaveAttribute("aria-pressed", "true"); // optimistic, then confirmed
  expect(writes).toEqual([{ method: "PUT", path: `/api/v1/products/${CATALOG[2].id}/watch`, body: null }]);
  await page.goto("/watchlists");
  await expect(nav(page).getByRole("button", { name: /Main/ })).toHaveAttribute("aria-current", "page");
  await expect(row(page, "Main", title)).toBeVisible();
});

test("move to another list, remove and undo within 5 s, keyboard only", async ({ page }) => {
  test.setTimeout(60_000);
  const { writes } = await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  const title = CATALOG[0].title;
  await page.getByRole("button", { name: `Actions for ${title}` }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Open product" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Move to" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("menuitem", { name: "Pet niche" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(toast(page)).toHaveText("Moved to Pet niche.");
  await expect(row(page, "Main", title)).toHaveCount(0);
  await expect(page.getByRole("link", { name: CATALOG[3].title, exact: true })).toBeFocused(); // the next row, not the page
  expect(writes.at(-1)).toEqual({ method: "POST", path: `/api/v1/watchlists/${MAIN}/items/move`, body: { product_ids: [CATALOG[0].id], to: PET } });

  await nav(page).getByRole("button", { name: /Pet niche/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/watchlists?list=${PET}`);
  await expect(row(page, "Pet niche", title)).toBeVisible();

  const remove = async () => {
    await page.getByRole("button", { name: `Actions for ${title}` }).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("End");
    await expect(page.getByRole("menuitem", { name: "Remove" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(row(page, "Pet niche", title)).toHaveCount(0); // hidden at once
    await expect(toast(page)).toContainText(`Removed ${title} from Pet niche.`);
  };
  await remove();
  await page.keyboard.press("Control+z");
  await expect(row(page, "Pet niche", title)).toBeVisible();
  await page.waitForTimeout(5500);
  expect(deletes(writes)).toEqual([]); // the undo sent nothing, ever
  await remove();
  await page.waitForTimeout(4000);
  expect(deletes(writes)).toEqual([]); // still inside the window
  await expect.poll(() => deletes(writes).length, { timeout: 4000 }).toBe(1);
  expect(deletes(writes)[0].path).toBe(`/api/v1/watchlists/${PET}/items/${CATALOG[0].id}`);
  await expect(row(page, "Pet niche", title)).toHaveCount(0);
  await expect(row(page, "Pet niche", CATALOG[7].title)).toBeVisible(); // after the refetch, the rest stay
});

test("bulk select moves and removes several rows; the Undo button restores them", async ({ page }) => {
  const { writes } = await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  for (const i of [0, 3]) {
    await page.getByRole("checkbox", { name: `Select ${CATALOG[i].title}` }).focus();
    await page.keyboard.press("Space");
  }
  const bar = page.getByRole("toolbar", { name: "Selected products" });
  await expect(bar).toContainText("2 selected");
  await bar.getByRole("button", { name: "Move to…" }).click();
  await page.getByRole("menuitem", { name: "Q4 gifts" }).click();
  await expect(toast(page)).toHaveText("Moved 2 products to Q4 gifts.");
  await expect(bar).toBeHidden();
  expect(writes.at(-1)?.body).toMatchObject({ product_ids: [CATALOG[0].id, CATALOG[3].id] });

  await page.getByRole("checkbox", { name: "Select all" }).check();
  await bar.getByRole("button", { name: "Remove" }).click();
  await expect(table(page, "Main")).toBeHidden(); // every row hidden: the empty state shows meanwhile
  await toast(page).getByRole("button", { name: "Undo" }).click();
  await expect(table(page, "Main").getByRole("row")).toHaveCount(3); // header + both rows back
  expect(deletes(writes)).toEqual([]);
});

test("lists are created, renamed and deleted with a confirmation", async ({ page }) => {
  await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  await nav(page).getByRole("button", { name: "New list" }).focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New list" });
  await expect(dialog.getByRole("textbox", { name: "List name" })).toBeFocused();
  await page.keyboard.type("Pet niche");
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("alert")).toBeVisible(); // a duplicate name is a 409
  await page.keyboard.press("Control+a");
  await page.keyboard.type("Gym gear");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(nav(page).getByRole("button", { name: /Gym gear/ })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "This list is empty" })).toBeVisible();

  await page.getByRole("button", { name: "Gym gear settings" }).click();
  await page.getByRole("menuitem", { name: "Rename…" }).click();
  await page.getByRole("textbox", { name: "List name" }).fill("Home gym");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Home gym", level: 2 })).toBeVisible();

  await page.getByRole("button", { name: "Home gym settings" }).click();
  await page.getByRole("menuitem", { name: "Delete list…" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete Home gym?" });
  await expect(confirm).toContainText("It's empty.");
  await confirm.getByRole("button", { name: "Delete list" }).click();
  await expect(nav(page).getByRole("button", { name: /Home gym/ })).toHaveCount(0);
  await expect(nav(page).getByRole("button", { name: /Main/ })).toHaveAttribute("aria-current", "page");
});

test("a merged product shows its survivor with a note; a missing number reads no source yet, never 0", async ({ page }) => {
  await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  const merged = row(page, "Main", CATALOG[12].title);
  await expect(merged).toContainText("Merged");
  await expect(merged).toContainText("you added Glow lamp (old listing), since merged into this product");
  await expect(merged.getByRole("link", { name: CATALOG[12].title })).toHaveAttribute("href", `/products/${CATALOG[12].id}`);
  const unmatched = row(page, "Main", CATALOG[5].title); // no store matched yet
  await expect(unmatched.getByRole("button", { name: /Retail price: No source yet/ })).toBeVisible();
  await expect(unmatched.getByRole("button", { name: /Stores selling it: No source yet/ })).toBeVisible();
  await expect(unmatched).not.toContainText("$0");
});

test("the Product Page Watch button and its lists menu", async ({ page }) => {
  await mockProductApi(page);
  const { writes } = await mockWatchlistsApi(page);
  await page.goto(`/products/${PRODUCT_ID}`);
  const watch = page.getByRole("button", { name: "Watch", exact: true });
  await watch.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Watching" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Lists for this product" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitemcheckbox", { name: /Main/ })).toHaveAttribute("aria-checked", "true");
  const pet = page.getByRole("menuitemcheckbox", { name: /Pet niche/ });
  await expect(pet).toHaveAttribute("aria-checked", "false");
  await pet.focus();
  await page.keyboard.press("Space");
  await expect(pet).toHaveAttribute("aria-checked", "true"); // the menu stays open
  expect(writes.at(-1)).toEqual({ method: "POST", path: `/api/v1/watchlists/${PET}/items`, body: { product_ids: [PRODUCT_ID] } });
});

test("a phone shows cards and a list dropdown, with no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockWatchlistsApi(page);
  await page.goto("/watchlists");
  const cards = page.getByRole("list", { name: "Main products" });
  await expect(cards.getByRole("article")).toHaveCount(4);
  await page.getByRole("combobox", { name: "Watchlist" }).selectOption({ label: "Pet niche (1)" });
  await expect(page.getByRole("list", { name: "Pet niche products" }).getByRole("article")).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
});

test("first visit, a failed load and a failed list each say what to do", async ({ page }) => {
  await mockWatchlistsApi(page, { store: { lists: [], items: [] } });
  await page.goto("/watchlists");
  await expect(page.getByRole("heading", { name: "Star products to watch them here" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Find products in Discover" })).toHaveAttribute("href", "/discover");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockWatchlistsApi(page, { listsStatus: 503 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Couldn't load your watchlists" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockWatchlistsApi(page, { itemsStatus: 503 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Couldn't load this list" })).toBeVisible();
});
