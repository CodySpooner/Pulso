import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-123 / imp-126 owner review screenshots, from fixtures only: 1440px and 375px, dark and light. A failed
// disable inside its dialog, a failed Run now, a failed dialog-less enable on a phone, and a tapped unavailable
// Run now. Run with `pnpm --filter web e2e:screenshots e2e/data-health/action-failures`; output: docs/screenshots/imp-123/.
const OUT = "../../docs/screenshots/imp-123";
const ID = "3f2b8c1e-7d4a-4e9b-9c5f-1a2b3c4d5e6f";

async function open(page: Page, theme: "dark" | "light", live = false) {
  await mockAdminApi(page, { host: { live_runs_allowed: live } });
  await page.route(/\/api\/v1\/admin\/sources\/[^/]+(\/run)?$/, (route) => route.fulfill({ status: 503, json: problem(503, ID) }));
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
  await page.goto("/admin/data-health");
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
}

async function shot(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
}

for (const theme of ["dark", "light"] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ] as const) {
    test.describe(`${width}px ${theme}`, () => {
      test.use({ viewport: { width, height } });

      test("disable fails inside its dialog", async ({ page }) => {
        await open(page, theme);
        await page.getByRole("switch", { name: "Google Trends enabled" }).click();
        const dialog = page.getByRole("dialog", { name: "Disable Google Trends?" });
        await dialog.getByRole("textbox").fill("pausing for review");
        await dialog.getByRole("button", { name: "Disable", exact: true }).focus();
        await page.keyboard.press("Enter"); // by keyboard, so Disable keeps a visible ring after the failure
        await expect(dialog.getByRole("alert")).toBeVisible();
        await shot(page, `toggle-failure-${width}-${theme}`);
      });

      test("Run now fails next to its button", async ({ page }) => {
        await open(page, theme, true);
        const run = page.getByRole("button", { name: "Run Google Trends now" });
        await run.focus();
        await page.keyboard.press("Enter");
        await expect(page.getByText("Couldn't start Google Trends").filter({ visible: true })).toBeVisible();
        await shot(page, `run-failure-${width}-${theme}`);
      });

      if (width === 375) {
        test("a dialog-less enable fails in its card", async ({ page }) => {
          await open(page, theme);
          const toggle = page.getByRole("switch", { name: "Frankfurter FX enabled" });
          await toggle.focus();
          await page.keyboard.press("Space");
          await expect(page.getByRole("listitem").filter({ has: toggle }).getByRole("alert")).toBeVisible();
          await shot(page, `enable-failure-${width}-${theme}`);
        });

        test.describe("touch", () => {
          test.use({ hasTouch: true });

          test("a tap on an unavailable Run now says why", async ({ page }) => {
            await open(page, theme);
            const run = page.getByRole("button", { name: "Run Google Trends now" });
            await run.scrollIntoViewIfNeeded();
            await run.tap({ force: true }); // aria-disabled
            await expect(page.getByRole("tooltip")).toBeVisible();
            await shot(page, `run-unavailable-tap-${width}-${theme}`);
          });
        });
      }
    });
  }
}
