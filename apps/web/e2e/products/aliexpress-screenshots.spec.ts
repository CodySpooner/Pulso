import { expect, test, type Page } from "@playwright/test";

import { aliexpress, mockAdminApi, sources } from "../data-health/fixtures";
import { empty, found, LINK, mockAliExpressApi, paused } from "./aliexpress-fixtures";
import { PRODUCT_ID } from "./fixtures";

// p3-05 (AE-3) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The Suppliers tab's
// AliExpress section loaded, empty, off, paused, loading, error, stale and refusing a link, plus Data Health's real
// AliExpress row. Run with `pnpm --filter web e2e:screenshots e2e/products/aliexpress`; output: docs/screenshots/p3-05/.
const OUT = "../../docs/screenshots/p3-05";
const URL = `/products/${PRODUCT_ID}?tab=suppliers`;
const section = (page: Page) => page.getByRole("region", { name: "AliExpress", exact: true });

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 1100],
    [375, 1400],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ hasTouch: width === 375 });
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      });

      // The section sits below the supplier table: bring it to the top of the viewport, then capture the view.
      const shot = async (page: Page, name: string) => {
        await page.evaluate(() => document.fonts.ready);
        await section(page).evaluate((el) => el.scrollIntoView({ block: "start" }));
        await page.waitForTimeout(300);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); // no page scroll sideways
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png` });
      };

      test("loaded", async ({ page }) => {
        await mockAliExpressApi(page, [found]);
        await page.goto(URL);
        await expect(page.getByLabel("AliExpress variants").filter({ visible: true })).toBeVisible(); // a table from 768 px, cards below
        await shot(page, "loaded");
      });

      test("empty", async ({ page }) => {
        await mockAliExpressApi(page, [empty]);
        await page.goto(URL);
        await expect(section(page)).toContainText("No lookup yet");
        await shot(page, "empty");
      });

      test("off", async ({ page }) => {
        await mockAliExpressApi(page, [{ status: "disabled" }]);
        await page.goto(URL);
        await expect(section(page)).toContainText("AliExpress is off");
        await shot(page, "off");
      });

      test("paused", async ({ page }) => {
        await mockAliExpressApi(page, [paused]);
        await page.goto(URL);
        await expect(section(page)).toContainText("Lookups resume at");
        await shot(page, "paused");
      });

      test("loading", async ({ page }) => {
        await mockAliExpressApi(page, ["hold"]);
        await page.goto(URL);
        await expect(section(page).locator(".bg-skeleton").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await mockAliExpressApi(page, [503]);
        await page.goto(URL);
        await expect(section(page)).toContainText("Couldn't load the AliExpress lookup");
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        await mockAliExpressApi(page, [found, 503]);
        await page.goto(URL);
        await expect(page.getByLabel("AliExpress variants").filter({ visible: true })).toBeVisible(); // a table from 768 px, cards below
        await page.clock.setFixedTime(new Date(Date.parse(found.as_of!) + 2 * 3_600_000 + 6 * 60_000));
        await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
        await expect(section(page)).toContainText("Couldn't refresh the AliExpress lookup");
        await shot(page, "stale");
      });

      test("wrong link", async ({ page }) => {
        await mockAliExpressApi(page, [found], 422);
        await page.goto(URL);
        await page.getByLabel("AliExpress product link or number").fill(LINK.replace("aliexpress.com", "example.com"));
        await page.getByRole("button", { name: "Look up" }).click();
        await expect(section(page).getByRole("alert")).toBeVisible();
        await shot(page, "wrong-link");
      });

      test("data health row", async ({ page }) => {
        await mockAdminApi(page, { sources: [...sources, aliexpress] });
        await page.goto("/admin/data-health");
        const row = page.getByRole("region", { name: "Sources table" }).getByRole("row", { name: /AliExpress/ });
        const card = page.getByRole("listitem").filter({ hasText: "AliExpressOfficial API" }); // the phone list's card
        const target = width === 1440 ? row : card;
        await expect(target).toContainText("Disabled");
        await page.evaluate(() => document.fonts.ready);
        await target.evaluate((el) => el.scrollIntoView({ block: "center" }));
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/data-health-row-${width}-${theme}.png` });
      });
    });
  }
}
