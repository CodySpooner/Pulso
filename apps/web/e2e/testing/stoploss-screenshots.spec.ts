import { expect, test, type Page } from "@playwright/test";

import { mockTestingApi, type TestingMock } from "./fixtures";

// p4-28 (WF-5c) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. Testing cards with the
// stop-loss and winner chips, day N and the spend bar; the drawer's "Changed since start" with changes, none, a calc
// that can't run, a missing value, loading and error. Run with
// `pnpm --filter web e2e:screenshots e2e/testing/stoploss-screenshots`; output: docs/screenshots/p4-28/.
const OUT = "../../docs/screenshots/p4-28";

const drawers: [string, number, TestingMock["sinceStart"]][] = [
  ["drawer-changes", 9, undefined],
  ["drawer-no-changes", 3, undefined],
  ["drawer-cant-run", 2, { 2: { changes: [], reason: "Supplier listing not found on this product.", as_of: null } }],
  [
    "drawer-no-source",
    8,
    {
      8: {
        changes: [
          { input: "freight_quote_id", old: 41, new: null },
          { input: "freight_minor", old: 400, new: null },
          { input: "margin_minor", old: 2433, new: null },
        ],
        reason: null,
        as_of: "2026-10-21T18:00:00Z",
      },
    },
  ],
  ["drawer-loading", 9, { 9: "hold" }],
  ["drawer-error", 9, { 9: "error" }],
];

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
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage });
      };

      test("testing cards", async ({ page }) => {
        await mockTestingApi(page);
        await page.goto("/testing");
        const column = page.getByRole("region", { name: /^Testing\b/ });
        await expect(column.getByText("Over stop-loss")).toBeVisible();
        if (width === 375) await column.scrollIntoViewIfNeeded();
        await shot(page, "board", width !== 375);
      });

      for (const [name, id, sinceStart] of drawers) {
        test(name, async ({ page }) => {
          await mockTestingApi(page, { sinceStart });
          await page.goto(`/testing?test=${id}`);
          const dialog = page.getByRole("dialog");
          await expect(dialog.getByRole("heading", { name: "Changed since start" })).toBeVisible();
          if (!name.endsWith("loading")) await expect(dialog.getByRole("status", { name: "Comparing with today's Profit calc" })).toHaveCount(0);
          await dialog.evaluate((el) => (el.scrollTop = el.scrollHeight)); // the comparison is the last section
          await shot(page, name, false);
        });
      }
    });
  }
}
