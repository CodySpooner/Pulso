import { expect, test, type Page } from "@playwright/test";

import { problem } from "../data-health/fixtures";
import { mockProductApi, product, PRODUCT_ID } from "../products/fixtures";
import { CATALOG, mockWatchlistsApi } from "./fixtures";

// imp-423: W toggles the ★ on the focused product, or the Product Page's Watch from anywhere, against fixture responses
// (the E2E auth bypass, never a database restore).
const cards = (page: Page) => page.getByRole("list", { name: "Products" }).getByRole("article");
const said = (page: Page, text: string) => page.getByText(text, { exact: true });
const writes = (log: { method: string; path: string }[]) => log.map((w) => [w.method, w.path]);
const empty = () => ({ store: { lists: [], items: [] } }); // fresh per test: the mock writes into its store

test("W on a focused Discover card stars it and says so; W again unstars it", async ({ page }) => {
  const { writes: log } = await mockWatchlistsApi(page, empty());
  await page.goto("/discover");
  const { id, title } = CATALOG[2];
  const card = cards(page).nth(2);
  const star = card.getByRole("button", { name: `Watch ${title}` });
  await expect(star).toHaveAttribute("aria-pressed", "false");
  await expect(star).toHaveAttribute("aria-keyshortcuts", "W");
  await card.getByRole("link", { name: title }).focus();
  await page.keyboard.press("w"); // one key from a focused product
  await expect(star).toHaveAttribute("aria-pressed", "true");
  await expect(said(page, `Added ${title} to Main`)).toBeAttached();
  await page.keyboard.press("w");
  await expect(star).toHaveAttribute("aria-pressed", "false");
  await expect(said(page, `Removed ${title} from Main`)).toBeAttached();
  await expect(card.getByRole("link", { name: title })).toBeFocused(); // focus stays on the product
  expect(writes(log)).toEqual([
    ["PUT", `/api/v1/products/${id}/watch`],
    ["DELETE", `/api/v1/products/${id}/watch`],
  ]);
});

test("W on a focused Discover table row; a failed watch flips back and says so", async ({ page }) => {
  await mockWatchlistsApi(page, empty());
  await page.route(/\/api\/v1\/products\/[^/]+\/watch$/, (route) => route.fulfill({ status: 503, contentType: "application/problem+json", json: problem(503, "e2e-watch-503") }));
  await page.goto("/discover?view=table");
  const { title } = CATALOG[1];
  const row = page.getByRole("region", { name: "Products" }).locator("tbody tr").nth(1);
  const star = row.getByRole("button", { name: `Watch ${title}` });
  await row.getByRole("link", { name: title }).focus();
  await page.keyboard.press("W"); // Shift+W is W too
  await expect(said(page, `Couldn't add ${title} to Main. Try again.`)).toBeAttached();
  await expect(star).toHaveAttribute("aria-pressed", "false");
  await expect(page).toHaveURL(/\/discover\?view=table$/); // the row didn't open
});

test("on the Product Page, W anywhere toggles Watch, but not while typing a note or in the lists menu", async ({ page }) => {
  await mockProductApi(page);
  const { writes: log } = await mockWatchlistsApi(page, empty());
  await page.goto(`/products/${PRODUCT_ID}`);
  const watch = page.getByRole("button", { name: "Watch", exact: true });
  await expect(watch).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("w"); // nothing focused
  await expect(page.getByRole("button", { name: "Watching" })).toHaveAttribute("aria-pressed", "true");
  await expect(said(page, `Added ${product.title} to Main`)).toBeAttached();

  await page.getByRole("textbox", { name: "Add a note" }).focus();
  await page.keyboard.type("wow");
  await expect(page.getByRole("textbox", { name: "Add a note" })).toHaveValue("wow");
  await page.getByRole("button", { name: "Lists for this product" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitemcheckbox", { name: /Main/ })).toBeFocused();
  await page.keyboard.press("w");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Watching" })).toHaveAttribute("aria-pressed", "true");
  expect(writes(log)).toEqual([["PUT", `/api/v1/products/${PRODUCT_ID}/watch`]]);
});
