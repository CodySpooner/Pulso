import { expect, test, type Page } from "@playwright/test";

import { NOW } from "../data-health/fixtures";
import { LATEST, mockPulseApi, nothing, pulse, type PulseMock } from "./fixtures";

// p4-29 (WF-6b) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The pulse with the
// Shopify crawler off, a past day, the movers' Down list, and the loading, error, stale and nothing-collected states.
// Run with `pnpm --filter web e2e:screenshots e2e/pulse`; output: docs/screenshots/p4-29/.
const OUT = "../../docs/screenshots/p4-29";

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
        await page.waitForTimeout(400);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true); // no sideways scroll
        // At lg only <main> scrolls, so a full-page shot is the viewport: grow it to the page instead.
        const tall = await page.evaluate(() => Math.ceil(document.querySelector("main")!.scrollHeight + document.querySelector("main")!.getBoundingClientRect().top));
        if (tall > height) await page.setViewportSize({ width, height: tall });
        await page.waitForTimeout(200);
        await page.screenshot({ path: `${OUT}/${name}-${width}-${theme}.png`, fullPage: true });
      };
      const open = async (page: Page, path = "/", options: PulseMock = {}) => {
        const api = await mockPulseApi(page, options);
        await page.goto(path);
        return api;
      };

      test("pulse", async ({ page }) => {
        await open(page);
        await expect(page.locator("section[data-status=ok]").first()).toBeVisible();
        await shot(page, "pulse");
      });

      test("past day, movers down", async ({ page }) => {
        await open(page, "/?date=2026-10-18");
        await page.getByRole("button", { name: "Down" }).click();
        await shot(page, "past-day");
      });

      test("loading", async ({ page }) => {
        await open(page, "/", { hold: true });
        await page.waitForTimeout(400); // past the skeleton's 150 ms delay
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await open(page, "/", { status: 503 });
        await expect(page.getByRole("heading", { name: "Couldn’t load the Daily Pulse" })).toBeVisible();
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        const options: PulseMock = { day: (d) => pulse(d ?? "2026-10-19") };
        await open(page, "/", options);
        await expect(page.locator("section[data-status=ok]").first()).toBeVisible();
        options.status = 503; // a refresh on focus fails: the day stays with the stale line over it
        await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000));
        await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
        await expect(page.getByRole("group", { name: "Couldn’t refresh the Daily Pulse" })).toBeVisible({ timeout: 15_000 });
        await shot(page, "stale");
      });

      test("nothing collected", async ({ page }) => {
        await open(page, "/", { day: (d) => nothing(d ?? LATEST) });
        await expect(page.getByRole("heading", { name: "Your first pulse arrives once collectors run" })).toBeVisible();
        await shot(page, "no-source");
      });
    });
  }
}
