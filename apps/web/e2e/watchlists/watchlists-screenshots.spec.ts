import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { CATALOG, MAIN, mockWatchlistsApi, PET, watchStore, type WatchMock } from "./fixtures";

// p4-13 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The list (a merged row, a stale
// row, no source yet), bulk selection with the undo toast, first visit, an empty list, loading, error, the delete
// confirmation, the ★ on Discover's grid and table, and the Product Page's Watch menu. Run with
// `pnpm --filter web e2e:screenshots e2e/watchlists`; output: docs/screenshots/p4-13/.
const OUT = "../../docs/screenshots/p4-13";

/** Main also holds product 8, whose store data is 3 days old: its row shows the stale dot. */
const withStale = () => {
  const store = watchStore();
  store.items.push({ list: MAIN, product_id: CATALOG[8].id, name: CATALOG[8].title, added_at: "2026-10-20T09:00:00Z" });
  return store;
};

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
      const phone = width === 375;
      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        // A view's fade waits on LazyMotion's features chunk after a full load: shoot once it has finished.
        await page.waitForFunction(() => [...document.querySelectorAll<HTMLElement>("main [style*='opacity']")].every((el) => el.closest("[role=status]") || getComputedStyle(el).opacity === "1"));
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };
      const open = async (page: Page, options: WatchMock = {}, path = "/watchlists") => {
        const api = await mockWatchlistsApi(page, { store: withStale(), ...options });
        await page.goto(path);
        return api;
      };
      const firstRow = (page: Page) => page.getByRole(phone ? "article" : "row").filter({ hasText: CATALOG[0].title }).first();

      test("list", async ({ page }) => {
        await open(page);
        await expect(firstRow(page)).toBeVisible();
        if (!phone) {
          // Every column, the row menu included, fits at 1440 px with a stale row's longest "Last seen".
          const region = page.getByRole("region", { name: "Main products" });
          expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
        }
        await shot(page, "list");
      });

      test("bulk and undo", async ({ page }) => {
        await open(page);
        if (phone) {
          await page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).click();
          await page.getByRole("menuitem", { name: "Remove" }).click();
        } else {
          for (const i of [3, 5]) await page.getByRole("checkbox", { name: `Select ${CATALOG[i].title}` }).check();
          await shot(page, "bulk");
          await page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).click();
          await page.getByRole("menuitem", { name: "Remove" }).click();
        }
        await expect(page.getByRole("button", { name: "Undo" })).toBeVisible();
        await shot(page, "undo");
      });

      test("row menu", async ({ page }) => {
        await open(page);
        await page.getByRole("button", { name: `Actions for ${CATALOG[0].title}` }).click();
        await page.getByRole("menuitem", { name: "Move to" }).click();
        await expect(page.getByRole("menuitem", { name: "Pet niche" })).toBeVisible();
        await shot(page, "move-menu");
      });

      test("first visit", async ({ page }) => {
        await open(page, { store: { lists: [], items: [] } });
        await expect(page.getByRole("heading", { name: "Star products to watch them here" })).toBeVisible();
        await shot(page, "empty");
      });

      test("empty list", async ({ page }) => {
        await open(page, {}, `/watchlists?list=a0000000-0000-4000-8000-000000000003`);
        await expect(page.getByRole("heading", { name: "This list is empty" })).toBeVisible();
        await shot(page, "empty-list");
      });

      test("loading", async ({ page }) => {
        await open(page, { holdItems: true });
        await expect(page.getByRole("status", { name: "Loading products" })).toBeVisible();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await open(page, { itemsStatus: 503 });
        await expect(page.getByRole("heading", { name: "Couldn't load this list" })).toBeVisible();
        await shot(page, "error");
      });

      test("delete confirmation", async ({ page }) => {
        await open(page, {}, `/watchlists?list=${PET}`);
        await page.getByRole("button", { name: "Pet niche settings" }).click();
        await page.getByRole("menuitem", { name: "Delete list…" }).click();
        await expect(page.getByRole("dialog", { name: "Delete Pet niche?" })).toBeVisible();
        await shot(page, "delete");
      });

      test("Discover grid and table", async ({ page }) => {
        await open(page, {}, "/discover");
        await expect(page.getByRole("button", { name: `Watch ${CATALOG[0].title}` }).first()).toHaveAttribute("aria-pressed", "true");
        await shot(page, "discover-grid");
        if (phone) return; // the phone table is Discover's own (p2-03); the grid is what a phone uses
        await page.goto("/discover?view=table");
        await expect(page.getByRole("button", { name: `Watch ${CATALOG[0].title}` })).toBeVisible();
        await shot(page, "discover-table");
      });

      test("Product Page Watch menu", async ({ page }) => {
        await mockProductApi(page);
        await mockWatchlistsApi(page, { store: withStale() });
        await page.goto(`/products/${PRODUCT_ID}`);
        await page.getByRole("button", { name: "Watch", exact: true }).click();
        await expect(page.getByRole("button", { name: "Watching" })).toBeVisible();
        await page.getByRole("button", { name: "Lists for this product" }).click();
        await expect(page.getByRole("menuitemcheckbox", { name: /Main/ })).toHaveAttribute("aria-checked", "true");
        await shot(page, "product-watch");
      });
    });
  }
}
