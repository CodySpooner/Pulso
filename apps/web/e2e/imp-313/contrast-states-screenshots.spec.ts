import { expect, test, type Page } from "@playwright/test";

import { SCREENS } from "../p2-39/screens";
import { PRODUCT_ID } from "../products/fixtures";
import { mockProfitApi } from "../products/profit-fixtures";

// imp-313 owner review: the p2-03 (Discover) and p2-15 (Settings) screens, Profit (also mid-recompute) and Trends,
// from fixtures only (the E2E auth bypass). Run with `pnpm --filter web e2e:screenshots e2e/imp-313`;
// output: docs/screenshots/imp-313/.
const OUT = "../../docs/screenshots/imp-313";

const screen = (name: string) => SCREENS.find((s) => s.name === name)!.open;

const SHOTS: { name: string; open: (page: Page) => Promise<unknown> }[] = [
  { name: "discover-grid", open: screen("discover-grid") },
  { name: "discover-table", open: screen("discover-table") },
  {
    name: "settings",
    open: async (page) => {
      await screen("settings")(page);
      await page.locator("#duty").scrollIntoViewIfNeeded(); // the duty selector, below the fold
    },
  },
  { name: "profit", open: screen("product-profit") },
  {
    name: "profit-recomputing",
    open: async (page) => {
      await mockProfitApi(page, { holdRecompute: true });
      await page.goto(`/products/${PRODUCT_ID}?tab=profit`);
      await expect(page.getByRole("tabpanel").locator("dl").first()).toContainText("Profit per order▲+$0.03");
      await page.getByRole("slider", { name: "Sell price", exact: true }).focus();
      await page.keyboard.press("ArrowRight");
      await expect(page.getByRole("tabpanel").locator("[aria-busy=true]")).toHaveCount(2);
    },
  },
  { name: "trends", open: screen("product-trends") },
];

for (const width of [1440, 375])
  test.describe(`${width}px`, () => {
    test.use({ hasTouch: width === 375 });
    for (const theme of ["dark", "light"] as const)
      for (const shot of SHOTS)
        test(`${shot.name} ${theme}`, async ({ page }) => {
          await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
          await page.emulateMedia({ colorScheme: theme });
          await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
          await shot.open(page);
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          await page.screenshot({ path: `${OUT}/${shot.name}-${width}-${theme}.png` });
        });
  });
