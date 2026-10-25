import { expect, test, type Page } from "@playwright/test";

import { NOW } from "../data-health/fixtures";
import { refocus } from "../settings/fixtures";
import { mockMatchingApi, title } from "./fixtures";

// p2-25 (UX-1) owner review screenshots, from fixtures only: 1440px and 375px, dark and light. The queue, the merge
// and split dialogs (desktop only: the phone is read-only), a decision with its undo toast, a pair that failed to
// load, loading, error, stale, queue clear and no source yet.
// Run with `pnpm --filter web e2e:screenshots e2e/matching/matching-screenshots`; output: docs/screenshots/p2-25/.
const OUT = "../../docs/screenshots/p2-25";
const pair = (page: Page, i: number) => page.getByRole("article", { name: `Listing A: ${title(i, "a")}` });

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

      test("queue", async ({ page }) => {
        await mockMatchingApi(page);
        await page.goto("/admin/matching");
        await expect(pair(page, 0)).toBeVisible();
        await shot(page, "queue");
      });

      if (width === 1440) {
        test("merge dialog", async ({ page }) => {
          await mockMatchingApi(page);
          await page.goto("/admin/matching");
          await expect(pair(page, 0)).toBeVisible();
          await page.keyboard.press("m");
          await expect(page.getByRole("dialog", { name: "Merge two products" })).toBeVisible();
          await shot(page, "merge", false);
        });

        test("split dialog", async ({ page }) => {
          await mockMatchingApi(page);
          await page.goto("/admin/matching");
          await expect(pair(page, 0)).toBeVisible();
          await page.keyboard.press("x");
          const split = page.getByRole("dialog", { name: "Split a product" });
          await split.getByRole("checkbox").first().check();
          await expect(split.getByRole("status")).toHaveText("1 move · 2 stay on Sunset projection lamp");
          await shot(page, "split", false);
        });
      }

      test("decided, with undo", async ({ page }) => {
        await mockMatchingApi(page);
        await page.goto("/admin/matching");
        await expect(pair(page, 0)).toBeVisible();
        await page.getByRole("toolbar", { name: "Decision" }).getByRole("button", { name: /^Accept/ }).click();
        await expect(pair(page, 1)).toBeVisible();
        await expect(page.getByText("Accepted pair #1000.")).toBeVisible();
        await shot(page, "decided", false);
      });

      test("pair failed to load", async ({ page }) => {
        await mockMatchingApi(page, { superseded: [1000], failDetail: [1001] });
        await page.goto("/admin/matching");
        await expect(page.getByRole("heading", { name: "Couldn't load pair #1001" })).toBeVisible();
        await shot(page, "pair-failed", false);
      });

      test("image unavailable", async ({ page }) => {
        await mockMatchingApi(page, { brokenImages: [1000], noImages: [1000] });
        await page.goto("/admin/matching");
        await expect(pair(page, 0).getByText("No image stored")).toBeVisible();
        await shot(page, "no-image");
      });

      test("loading", async ({ page }) => {
        await mockMatchingApi(page, { hold: true });
        await page.goto("/admin/matching");
        await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
        await shot(page, "loading");
      });

      test("error", async ({ page }) => {
        await mockMatchingApi(page, { status: 503 });
        await page.goto("/admin/matching");
        await expect(page.getByRole("heading", { name: "Couldn't load the queue" })).toBeVisible();
        await shot(page, "error");
      });

      test("stale", async ({ page }) => {
        const api = await mockMatchingApi(page);
        await page.goto("/admin/matching");
        await expect(pair(page, 0)).toBeVisible();
        api.failLists();
        await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000));
        await refocus(page);
        await expect(page.getByText(/Couldn't refresh the queue/)).toBeVisible();
        await shot(page, "stale", false);
      });

      test("queue clear", async ({ page }) => {
        await mockMatchingApi(page, { count: 0 });
        await page.goto("/admin/matching");
        await expect(page.getByRole("heading", { name: "Queue clear" })).toBeVisible();
        await shot(page, "queue-clear");
      });

      test("no source yet", async ({ page }) => {
        await mockMatchingApi(page, { count: 0, summary: { stored_sources: ["cj"] } });
        await page.goto("/admin/matching");
        await expect(page.getByRole("heading", { name: "Matching needs at least two stored sources" })).toBeVisible();
        await shot(page, "no-source");
      });
    });
  }
}
