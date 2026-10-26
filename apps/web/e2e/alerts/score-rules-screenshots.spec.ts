import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { alerts, lists, mockAlertsApi, scoreAlerts, scoreRules } from "./fixtures";

// p4-34 (WF-4d, DEC-353) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Rules tab
// with a velocity spike skipped over a data gap and a Saturation cross with no source yet, the builder's two new verbs
// (one on a watchlist), a 422 beside the Saturation line, and the inbox with both alerts. Run with
// `pnpm --filter web e2e:screenshots e2e/alerts/score-rules-screenshots`; output: docs/screenshots/p4-34/.
const OUT = "../../docs/screenshots/p4-34";

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

      const builder = async (page: Page, verb: string) => {
        await mockProductApi(page);
        await mockAlertsApi(page, { lists: lists() });
        await page.goto(`/products/${PRODUCT_ID}`);
        await page.getByRole("button", { name: "Create alert" }).click();
        const dialog = page.getByRole("dialog");
        await dialog.getByRole("combobox", { name: "Event" }).selectOption(verb);
        return dialog;
      };

      test("rules", async ({ page }) => {
        await mockAlertsApi(page, { rules: scoreRules() });
        await page.goto("/alerts?view=rules");
        await expect(page.getByRole("region", { name: "Alert rules" })).toBeVisible();
        await shot(page, "rules");
      });

      test("builder-velocity", async ({ page }) => {
        await builder(page, "velocity_spike");
        await shot(page, "builder-velocity", false);
      });

      test("builder-saturation-422", async ({ page }) => {
        const dialog = await builder(page, "saturation_cross");
        await dialog.getByRole("combobox", { name: "Watch" }).selectOption({ label: "any product on Pet" });
        await dialog.getByRole("textbox", { name: "Saturation, 0–100" }).fill("130");
        await dialog.getByRole("button", { name: "Create rule" }).click();
        await expect(dialog.getByRole("alert")).toBeVisible();
        await shot(page, "builder-saturation-422", false);
      });

      test("inbox", async ({ page }) => {
        await mockAlertsApi(page, { items: [...scoreAlerts(), ...alerts()] });
        await page.goto("/alerts");
        await expect(page.getByText("Velocity spiked")).toBeVisible();
        await shot(page, "inbox");
      });
    });
  }
}
