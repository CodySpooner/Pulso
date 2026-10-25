import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, overviewStale, overviewUnmatched, PRODUCT_ID, stale, unmatched } from "./fixtures";

// p2-07 (UX-4) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Overview tab and
// the context rail loaded with a provenance card open, then loading, no source yet, stale, error and a failed save.
// Run with `pnpm --filter web e2e:screenshots e2e/products/overview-screenshots`; output: docs/screenshots/p2-07/.
const OUT = "../../docs/screenshots/p2-07";
const URL = `/products/${PRODUCT_ID}`;

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
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage: true });
      };

      test("loaded, card open", async ({ page }) => {
        await mockProductApi(page);
        await page.goto(URL);
        const cost = page.getByRole("button", { name: "Best supplier cost: $8.12" });
        if (width === 375) await cost.tap();
        else await cost.focus();
        await expect(page.locator('[role="tooltip"]')).toContainText("Raw payload");
        await shot(page, "loaded");
      });

      test("loading", async ({ page }) => {
        await mockProductApi(page, { holdOverview: true });
        await page.goto(URL);
        await expect(page.getByRole("tabpanel").locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("no source yet", async ({ page }) => {
        await mockProductApi(page, { body: unmatched, overview: overviewUnmatched, notes: [], tags: [] });
        await page.goto(URL);
        await expect(page.getByText("No in-stock supplier offer yet.")).toBeVisible();
        await shot(page, "no-source");
      });

      test("stale", async ({ page }) => {
        await mockProductApi(page, { body: stale, overview: overviewStale });
        await page.goto(URL);
        await expect(page.getByText("Shopify stores · 3d ago · stale").first()).toBeVisible();
        await shot(page, "stale");
      });

      test("error", async ({ page }) => {
        await mockProductApi(page, { overviewStatus: 503 });
        await page.goto(URL);
        await expect(page.getByRole("heading", { name: "Couldn't load the overview" })).toBeVisible();
        await shot(page, "error");
      });

      test("save failed", async ({ page }) => {
        await mockProductApi(page, { failSaves: true });
        await page.goto(URL);
        const box = page.getByRole("textbox", { name: "Add a note" });
        await box.fill("Ask CJ for a US warehouse quote");
        await box.press("Control+Enter");
        await expect(page.getByRole("alert").filter({ hasText: "Couldn't add the note" })).toBeVisible();
        await box.blur();
        await shot(page, "save-failed");
      });
    });
  }
}
