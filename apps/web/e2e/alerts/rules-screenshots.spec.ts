import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { mockAlertsApi, ruleList } from "./fixtures";

// p4-27 (WF-4c) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Rules tab, the
// builder from the Product Page and in edit, a 422 by its field, and the loading, empty, error and stale states. Run
// with `pnpm --filter web e2e:screenshots e2e/alerts/rules-screenshots`; output: docs/screenshots/p4-27/.
const OUT = "../../docs/screenshots/p4-27";

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

      const shot = async (page: Page, name: string, fullPage = true) => {
        await page.evaluate(() => document.fonts.ready);
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); // no sideways scroll
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
      };

      test("rules", async ({ page }) => {
        await mockAlertsApi(page, { rules: ruleList() });
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("region", { name: "Alert rules" })).toBeVisible();
        await shot(page, "rules");
      });

      test("builder", async ({ page }) => {
        await mockProductApi(page);
        await mockAlertsApi(page);
        await page.goto(`/products/${PRODUCT_ID}`);
        await page.getByRole("button", { name: "Create alert" }).click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await shot(page, "builder", false);
      });

      test("builder-edit-422", async ({ page }) => {
        await mockAlertsApi(page, { rules: ruleList() });
        await page.goto("/alerts?view=rules");
        await page.getByRole("button", { name: "Edit: Lamp: supplier price ±8%" }).click();
        const dialog = page.getByRole("dialog");
        await dialog.getByRole("textbox", { name: "Change, %" }).fill("0");
        await dialog.getByRole("button", { name: "Save rule" }).click();
        await expect(dialog.getByRole("alert")).toBeVisible();
        await shot(page, "builder-edit-422", false);
      });

      test("loading", async ({ page }) => {
        await mockAlertsApi(page, { holdRules: true });
        await page.goto("/alerts?view=rules");
        await page.waitForTimeout(400);
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockAlertsApi(page, { rules: [] });
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("heading", { name: "No rules yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockAlertsApi(page, { rulesStatus: 503 });
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("heading", { name: "Couldn’t load your rules" })).toBeVisible();
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        const options: Parameters<typeof mockAlertsApi>[1] = { rules: ruleList().map((r) => ({ ...r, last_evaluated_at: r.last_evaluated_at && "2026-10-20T06:00:00Z" })) };
        await mockAlertsApi(page, options);
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("region", { name: "Alert rules" })).toBeVisible();
        options.rulesStatus = 503; // the write succeeds, and the refetch it starts fails
        await page.getByRole("switch", { name: "Notify: Lamp: stock-out" }).click();
        await expect(page.getByText("Couldn’t refresh rules.")).toBeVisible();
        await shot(page, "stale");
      });
    });
  }
}
