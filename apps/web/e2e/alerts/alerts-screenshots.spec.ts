import { expect, test, type Page } from "@playwright/test";

import { mockAlertsApi, rules } from "./fixtures";

// p4-22 (WF-4b) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The bell's popover,
// the inbox, a selection, Archived, and the loading, empty, error and stale states. Run with
// `pnpm --filter web e2e:screenshots e2e/alerts/alerts-screenshots`; output: docs/screenshots/p4-22/.
const OUT = "../../docs/screenshots/p4-22";

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

      test("popover", async ({ page }) => {
        await mockAlertsApi(page);
        await page.goto("/alerts");
        await page.getByTestId("alerts-bell").click();
        await expect(page.getByRole("menuitem", { name: /Supplier price rose/ })).toBeVisible();
        await shot(page, "popover", false);
      });

      test("inbox", async ({ page }) => {
        await mockAlertsApi(page);
        await page.goto("/alerts");
        await page.getByRole("checkbox", { name: /^Select Freight fell/ }).check();
        await shot(page, "inbox");
      });

      test("archived", async ({ page }) => {
        const api = await mockAlertsApi(page);
        api.rows[2].archived = true;
        await page.goto("/alerts?view=archived");
        await expect(page.getByRole("region", { name: "Archived alerts" })).toBeVisible();
        await shot(page, "archived");
      });

      test("loading", async ({ page }) => {
        await mockAlertsApi(page, { hold: true });
        await page.goto("/alerts");
        await page.waitForTimeout(400); // past the skeleton's 150 ms delay
        await shot(page, "loading");
      });

      test("empty", async ({ page }) => {
        await mockAlertsApi(page, { items: [], rules: rules().map((r) => ({ ...r, status: "no_source", skipped: null })) });
        await page.goto("/alerts");
        await expect(page.getByRole("heading", { name: "No alerts yet" })).toBeVisible();
        await shot(page, "empty");
      });

      test("error", async ({ page }) => {
        await mockAlertsApi(page, { status: 503 });
        await page.goto("/alerts");
        await expect(page.getByRole("heading", { name: "Couldn’t load alerts" })).toBeVisible();
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        const options: Parameters<typeof mockAlertsApi>[1] = { rules: rules().map((r) => ({ ...r, last_evaluated_at: "2026-10-20T06:00:00Z" })) };
        await mockAlertsApi(page, options);
        await page.goto("/alerts");
        await expect(page.getByRole("region", { name: "Alerts inbox" })).toBeVisible();
        options.status = 503; // the write succeeds, and the refetch it starts fails
        await page.getByRole("button", { name: "Mark all read" }).click();
        await expect(page.getByText("Couldn’t refresh alerts.")).toBeVisible();
        await shot(page, "stale");
      });
    });
  }
}
