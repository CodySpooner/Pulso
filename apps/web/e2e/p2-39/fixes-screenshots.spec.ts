import { expect, test, type Page } from "@playwright/test";

import { mockPopularApi } from "../google-popular/fixtures";
import { mockMatchingApi, title } from "../matching/fixtures";
import { mockProductApi, overview, PRODUCT_ID } from "../products/fixtures";
import { mockSearchApi, openPalette } from "../search/fixtures";

// p2-39 (Phase 2 end) owner review screenshots of each visible fix, from fixtures only (the E2E auth bypass). Run with
// `pnpm --filter web e2e:screenshots e2e/p2-39`; output: docs/screenshots/p2-39/. The "before" set in
// docs/screenshots/p2-39/before/ came from the same spec on origin/main 16abd9a with P239_OUT pointing there.
const OUT = process.env.P239_OUT ?? "../../docs/screenshots/p2-39";

interface Shot {
  name: string;
  width: number;
  open: (page: Page) => Promise<unknown>;
  /** The part of the page the fix changed; the whole viewport when absent. */
  target?: (page: Page) => ReturnType<Page["locator"]>;
}

const SHOTS: Shot[] = [
  {
    name: "palette-active-row",
    width: 1440,
    open: async (page) => {
      await mockSearchApi(page);
      const input = await openPalette(page);
      await input.pressSequentially("glow", { delay: 20 });
      await expect(page.getByRole("option", { name: /^Shenzhen Glowtech Co\./ })).toBeVisible();
    },
    target: (page) => page.getByRole("dialog"),
  },
  {
    name: "rail-saving-note",
    width: 1440,
    open: async (page) => {
      await mockProductApi(page, { holdSaves: true });
      await page.goto(`/products/${PRODUCT_ID}`);
      await page.getByRole("textbox", { name: "Add a note" }).fill("Pending thought");
      await page.getByRole("button", { name: "Add note" }).click();
      await expect(page.getByText("Saving…")).toBeVisible();
    },
    target: (page) => page.getByRole("region", { name: "Notes" }),
  },
  {
    name: "overview-gap-chip",
    width: 1440,
    open: async (page) => {
      await mockProductApi(page, { overview: { ...overview, velocity: { ...overview.velocity, gap: true } as typeof overview.velocity } });
      await page.goto(`/products/${PRODUCT_ID}`);
      await expect(page.getByText("gap", { exact: true })).toBeVisible();
    },
    target: (page) => page.locator("section[aria-labelledby=key-stats]"),
  },
  {
    name: "matching-score",
    width: 1440,
    open: async (page) => {
      await mockMatchingApi(page);
      await page.goto("/admin/matching");
      await expect(page.getByRole("article", { name: `Listing A: ${title(0, "a")}` })).toBeVisible();
    },
    target: (page) => page.locator("section[aria-labelledby=scores-title]"),
  },
  {
    name: "matching-filters",
    width: 375,
    open: async (page) => {
      await mockMatchingApi(page);
      await page.goto("/admin/matching");
      await expect(page.getByRole("article", { name: `Listing A: ${title(0, "a")}` })).toBeVisible();
    },
    target: (page) => page.getByRole("group", { name: "Sort and filter" }),
  },
  {
    name: "google-popular-header",
    width: 1440,
    open: async (page) => {
      await mockPopularApi(page);
      await page.goto("/google-popular");
      await expect(page.getByRole("main").getByRole("row").nth(1)).toBeVisible();
    },
  },
  { name: "coming-soon-stores", width: 1440, open: (page) => page.goto("/stores") },
  { name: "coming-soon-stores", width: 375, open: (page) => page.goto("/stores") },
];

for (const width of [1440, 375])
  test.describe(`${width}px`, () => {
    test.use({ hasTouch: width === 375 });
    for (const theme of ["dark", "light"] as const)
      for (const shot of SHOTS.filter((s) => s.width === width))
        test(`${shot.name} ${theme}`, async ({ page }) => {
          await page.setViewportSize({ width, height: width === 375 ? 812 : 900 });
          await page.emulateMedia({ colorScheme: theme });
          await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
          await shot.open(page);
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          const path = `${OUT}/${shot.name}-${width}-${theme}.png`;
          await (shot.target ? shot.target(page).screenshot({ path }) : page.screenshot({ path }));
        });
  });
