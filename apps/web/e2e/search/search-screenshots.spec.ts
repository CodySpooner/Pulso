import { expect, test, type Page } from "@playwright/test";

import { mockSearchApi, openPalette, type SearchMock } from "./fixtures";

// p2-16 (UX-9) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The palette with
// results in every group, then loading (first query), stale results under the spinner, no matches, no source yet and
// the error. Run with `pnpm --filter web e2e:screenshots e2e/search/search-screenshots`; output: docs/screenshots/p2-16/.
const OUT = "../../docs/screenshots/p2-16";

const STATES: { name: string; mock: SearchMock; type: string[]; ready: (page: Page) => Promise<void> }[] = [
  { name: "results", mock: {}, type: ["glow"], ready: (page) => expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible() },
  {
    name: "loading",
    mock: { hold: ["glow"] },
    type: ["glow"],
    ready: (page) => expect(page.getByRole("option", { name: "Searching products, stores and suppliers…" })).toBeVisible(),
  },
  {
    name: "stale",
    mock: { hold: ["glowb"] },
    type: ["glow", "glowb"],
    ready: async (page) => {
      await expect(page.getByTestId("palette-busy")).toBeVisible();
      await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible();
    },
  },
  { name: "empty", mock: {}, type: ["zzqx"], ready: (page) => expect(page.getByRole("option", { name: /No matches/ })).toBeVisible() },
  { name: "no-source", mock: { catalogEmpty: true }, type: ["glow"], ready: (page) => expect(page.getByRole("option", { name: /Nothing collected yet/ })).toBeVisible() },
  { name: "error", mock: { failures: 2 }, type: ["glow"], ready: (page) => expect(page.getByRole("option", { name: "Retry search" })).toBeVisible() },
];

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test.describe(`${width}px ${theme}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width, height });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      });

      for (const state of STATES) {
        test(state.name, async ({ page }) => {
          await mockSearchApi(page, state.mock);
          const input = await openPalette(page);
          for (const q of state.type) {
            await input.fill(q);
            if (q !== state.type.at(-1)) await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible();
          }
          await state.ready(page);
          await page.evaluate(() => document.fonts.ready);
          await page.waitForTimeout(300);
          await page.screenshot({ path: `${OUT}/${state.name}-${width}-${theme}.png` });
        });
      }
    });
  }
}
