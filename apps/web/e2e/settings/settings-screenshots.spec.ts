import { expect, test, type Page } from "@playwright/test";

import { NOW } from "../data-health/fixtures";
import { firstRun, mockSettingsApi, refocus } from "./fixtures";

// p2-15 (UX-10) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The configured form,
// the first run (duty not set, the "no source yet" state), invalid input, a failed save, saved, loading, error and stale.
// Run with `pnpm --filter web e2e:screenshots e2e/settings/settings-screenshots`; output: docs/screenshots/p2-15/.
const OUT = "../../docs/screenshots/p2-15";
const field = (page: Page, label: string) => page.getByRole("textbox", { name: label });

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
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
      };

      test("configured", async ({ page }) => {
        await mockSettingsApi(page);
        await page.goto("/settings");
        await expect(field(page, "Processing rate")).toHaveValue("2.9");
        await shot(page, "configured");
      });

      test("first run, duty not set", async ({ page }) => {
        await mockSettingsApi(page, { settings: firstRun });
        await page.goto("/settings");
        await expect(page.getByText("Duty not set.")).toBeVisible();
        await shot(page, "first-run");
      });

      test("invalid input", async ({ page }) => {
        await mockSettingsApi(page);
        await page.goto("/settings");
        await field(page, "Fixed fee per order").fill("0.305");
        await field(page, "Return rate").fill("101");
        await page.getByRole("button", { name: "Save changes" }).click();
        await expect(page.getByText("Fix 2 fields to save")).toBeVisible();
        await shot(page, "invalid");
      });

      test("save failed", async ({ page }) => {
        await mockSettingsApi(page, { failSaves: true });
        await page.goto("/settings");
        await field(page, "Processing rate").fill("3.1");
        await page.getByRole("button", { name: "Save changes" }).click();
        await expect(page.getByText("Couldn't save.")).toBeVisible();
        await shot(page, "save-failed", false); // the viewport, with the sticky bar where the owner sees it
      });

      test("saved", async ({ page }) => {
        await mockSettingsApi(page);
        await page.goto("/settings");
        await field(page, "Processing rate").fill("3.4");
        await page.keyboard.press("Control+s");
        await expect(page.getByText("Saved.")).toBeVisible();
        await shot(page, "saved", false);
      });

      test("loading", async ({ page }) => {
        await mockSettingsApi(page, { hold: true });
        await page.goto("/settings");
        await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await mockSettingsApi(page, { status: 503 });
        await page.goto("/settings");
        await expect(page.getByRole("heading", { name: "Couldn't load your settings" })).toBeVisible();
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        const api = await mockSettingsApi(page);
        await page.goto("/settings");
        await expect(field(page, "Processing rate")).toHaveValue("2.9");
        api.failGets();
        await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000));
        await refocus(page);
        await expect(page.getByRole("group", { name: "Couldn't refresh your settings" })).toBeVisible();
        await shot(page, "stale");
      });
    });
  }
}
