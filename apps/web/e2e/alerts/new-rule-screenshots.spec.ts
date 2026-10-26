import { expect, test, type Page } from "@playwright/test";

import { mockSearchApi, type SearchMock } from "../search/fixtures";
import { lists, mockAlertsApi, ruleList } from "./fixtures";

// imp-527 / imp-585 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Rules tab's
// New rule, the product picker's states, the builder after a product or a watchlist, and a 422 in words. Run with
// `pnpm --filter web e2e:screenshots e2e/alerts/new-rule-screenshots`; output: docs/screenshots/imp-527/.
const OUT = "../../docs/screenshots/imp-527";

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

      const shot = async (page: Page, name: string, fullPage = false) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); // no sideways scroll
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
      };
      const picker = async (page: Page, search: SearchMock = {}, rules = ruleList()) => {
        await mockSearchApi(page, search);
        await mockAlertsApi(page, { rules, lists: lists() });
        await page.goto("/alerts?view=rules");
        await page.getByRole("button", { name: "New rule" }).click();
        return page.getByRole("combobox", { name: "Product or watchlist" });
      };

      test("rules", async ({ page }) => {
        await mockAlertsApi(page, { rules: ruleList() });
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("region", { name: "Alert rules" })).toBeVisible();
        await shot(page, "rules", true);
      });

      test("rules-empty", async ({ page }) => {
        await mockAlertsApi(page, { rules: [] });
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("heading", { name: "No rules yet" })).toBeVisible();
        await shot(page, "rules-empty", true);
      });

      test("picker", async ({ page }) => {
        await expect(await picker(page)).toBeFocused();
        await shot(page, "picker");
      });

      test("picker-results", async ({ page }) => {
        await (await picker(page)).fill("glow");
        await expect(page.getByRole("option", { name: /^Glow-in-the-dark/ })).toBeVisible();
        await shot(page, "picker-results");
      });

      test("picker-loading", async ({ page }) => {
        await (await picker(page, { hold: ["lamp"] })).fill("lamp");
        await expect(page.getByRole("option", { name: "Searching products…" })).toBeVisible();
        await shot(page, "picker-loading");
      });

      test("picker-stale", async ({ page }) => {
        const search = await picker(page, { hold: ["glow l"] });
        await search.fill("glow");
        await expect(page.getByRole("option", { name: /^Glow-in-the-dark/ })).toBeVisible();
        await search.fill("glow l");
        await expect(page.getByTestId("picker-busy")).toBeVisible();
        await shot(page, "picker-stale");
      });

      test("picker-empty", async ({ page }) => {
        await (await picker(page)).fill("zzzz");
        await expect(page.getByRole("option", { name: /^No products match/ })).toBeVisible();
        await shot(page, "picker-empty");
      });

      test("picker-error", async ({ page }) => {
        await (await picker(page, { failures: 2 })).fill("lamp");
        await expect(page.getByRole("option", { name: /^Search unavailable/ })).toBeVisible();
        await shot(page, "picker-error");
      });

      test("picker-no-source", async ({ page }) => {
        await (await picker(page, { catalogEmpty: true })).fill("lamp");
        await expect(page.getByRole("option", { name: /^No products collected yet/ })).toBeVisible();
        await shot(page, "picker-no-source");
      });

      test("builder-product", async ({ page }) => {
        await (await picker(page)).fill("lamp");
        await page.getByRole("option", { name: /^Sunset projection lamp/ }).click();
        await expect(page.getByRole("combobox", { name: "Watch" })).toBeFocused();
        await shot(page, "builder-product");
      });

      test("builder-watchlist-422", async ({ page }) => {
        await picker(page);
        await page.getByRole("option", { name: /^Any product on Pet/ }).click();
        const dialog = page.getByRole("dialog");
        await dialog.getByRole("combobox", { name: "Event" }).selectOption("saturation_cross");
        await dialog.getByRole("textbox", { name: "Saturation, 0–100" }).fill("130");
        await dialog.getByRole("button", { name: "Create rule" }).click();
        await expect(dialog.getByRole("alert")).toHaveText("Saturation runs from 0 to 100.");
        await shot(page, "builder-watchlist-422");
      });
    });
  }
}
