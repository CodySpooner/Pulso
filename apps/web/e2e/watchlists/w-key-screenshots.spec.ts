import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { CATALOG, mockWatchlistsApi } from "./fixtures";

// imp-423 screenshots, from fixtures only: 1440px and 375px, dark and light. A Discover card starred with W while
// focused, and the Product Page's Watch after W. Run with `pnpm --filter web e2e:screenshots e2e/watchlists/w-key`;
// output: docs/screenshots/imp-423/.
const OUT = "../../docs/screenshots/imp-423";
const empty = () => ({ store: { lists: [], items: [] } }); // fresh per test: the mock writes into its store

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      });
      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForFunction(() => [...document.querySelectorAll<HTMLElement>("main [style*='opacity']")].every((el) => getComputedStyle(el).opacity === "1"));
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      };

      test("Discover card starred with W", async ({ page }) => {
        await mockWatchlistsApi(page, empty());
        await page.goto("/discover");
        const card = page.getByRole("list", { name: "Products" }).getByRole("article").nth(1);
        await card.getByRole("link", { name: CATALOG[1].title }).focus();
        await page.keyboard.press("w");
        await expect(page.getByText(`Added ${CATALOG[1].title} to Main`, { exact: true })).toBeAttached();
        await card.scrollIntoViewIfNeeded();
        await shot(page, "discover-card-w");
      });

      test("Product Page Watch after W", async ({ page }) => {
        await mockProductApi(page);
        await mockWatchlistsApi(page, empty()); // after the product routes, so its watch route answers
        await page.goto(`/products/${PRODUCT_ID}`);
        await expect(page.getByRole("button", { name: "Watch", exact: true })).toBeVisible();
        await page.keyboard.press("w");
        await expect(page.getByRole("button", { name: "Watching" })).toHaveAttribute("aria-pressed", "true");
        await shot(page, "product-page-w");
      });
    });
  }
}
