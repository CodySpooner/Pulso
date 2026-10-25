import { expect, test, type Page } from "@playwright/test";

import { LAYOUT } from "../../src/app/(app)/products/[id]/trends-model";
import { mockProductApi, PRODUCT_ID } from "./fixtures";
import { GAP_DAYS, mockSeriesApi, noHistory, shortHistory, staleSeries, trendsSeries } from "./trends-fixtures";

// p2-09 (UX-5) Trends tab against fixture series (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}?tab=trends`;
const DAY = 86_400_000;
const canvas = (page: Page) => page.getByTestId("trends-canvas");
const missing = (page: Page) => page.getByRole("list", { name: "Panes without data" });

async function open(page: Page, query = "", options: Parameters<typeof mockSeriesApi>[1] = {}) {
  await mockProductApi(page);
  const calls = await mockSeriesApi(page, options);
  await page.goto(`${URL}${query}`);
  return calls;
}

/** Share of painted pixels in a box of the canvas: a hatched band paints every pixel, an empty plot almost none. */
async function painted(page: Page, x: number, y: number, size = 8) {
  return canvas(page).evaluate(
    (el, [x, y, size]) => {
      const c = el.querySelector("canvas");
      const ratio = window.devicePixelRatio;
      const data = c!.getContext("2d")!.getImageData((x - size / 2) * ratio, y * ratio, size * ratio, size * ratio).data;
      let on = 0;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 0) on++;
      return on / (data.length / 4);
    },
    [x, y, size],
  );
}

test("gap days from coverage render as hatched bands; a day with no record is a break without one", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // no first-draw animation to wait out
  await open(page, "&range=30d");
  await expect(page.getByText("Collection gap · 3 days, no data")).toBeVisible();
  const box = (await canvas(page).boundingBox())!;
  // Grid geometry from LAYOUT; the price pane is second.
  const end = Date.parse(`${trendsSeries.end}T00:00:00Z`) + DAY;
  const x = (iso: string) => LAYOUT.left + ((Date.parse(`${iso}T12:00:00Z`) - (end - 30 * DAY)) / (30 * DAY)) * (box.width - LAYOUT.left - LAYOUT.right);
  const priceTop = LAYOUT.header + LAYOUT.pane + LAYOUT.header + LAYOUT.inset;
  const unrecorded = new Date(Date.parse(`${GAP_DAYS[0]}T00:00:00Z`) - 5 * DAY).toISOString().slice(0, 10); // day -14
  for (const day of GAP_DAYS) expect(await painted(page, x(day), priceTop + 6)).toBeGreaterThan(0.9);
  expect(await painted(page, x(unrecorded), priceTop + 6)).toBeLessThan(0.3);
  // Every pane with data marks the same source's gaps; the summary counts them for screen readers.
  await expect(canvas(page)).toHaveAttribute("aria-label", /3 collection gap days\./);
});

test("range and pane toggles take one click each, live in the URL and never refetch", async ({ page }) => {
  const calls = await open(page);
  await expect(page.getByRole("button", { name: "90D" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "7D" }).click();
  await expect(page).toHaveURL(`${URL}&range=7d`);
  await expect(canvas(page)).toHaveAttribute("aria-label", new RegExp(`^Trends chart, \\w+ \\d+ to \\w+ \\d+ UTC`));
  await page.getByRole("group", { name: "Panes" }).getByRole("button", { name: "Stores selling it" }).click();
  await expect(page).toHaveURL(`${URL}&range=7d&overlay=demand%2Cprice`);
  await expect(page.getByRole("group", { name: "Panes" }).getByRole("button", { name: "Stores selling it" })).toHaveAttribute("aria-pressed", "false");
  await expect(canvas(page)).not.toHaveAttribute("aria-label", /Stores selling it/);
  await page.reload();
  await expect(page.getByRole("button", { name: "7D" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "All" }).click();
  await page.getByRole("group", { name: "Panes" }).getByRole("button", { name: "Stores selling it" }).click();
  await expect(page).toHaveURL(`${URL}&range=all`); // every pane on again: the overlay param leaves
  expect(calls.map((u) => u.searchParams.get("range"))).toEqual(["all", "all"]); // one per page load, the whole history
});

test("a second click before the tab re-renders still builds on the first", async ({ page }) => {
  await open(page);
  const range = page.getByRole("button", { name: "7D" });
  const pane = page.getByRole("group", { name: "Panes" }).getByRole("button", { name: "Stores selling it" });
  await expect(pane).toBeVisible();
  // imp-278: Next syncs useSearchParams in a transition, so two clicks in one task always beat the re-render,
  // as a quick double tap on a slow device (or a busy CI runner) can.
  await page.evaluate((buttons) => { for (const b of buttons) (b as HTMLButtonElement).click(); }, [await range.elementHandle(), await pane.elementHandle()]);
  await expect(page).toHaveURL(`${URL}&range=7d&overlay=demand%2Cprice`);
  await expect(range).toHaveAttribute("aria-pressed", "true");
  await expect(pane).toHaveAttribute("aria-pressed", "false");
});

test("each pane shows its source and as of; the keyboard reads any day with its source and as of", async ({ page }) => {
  await open(page);
  await expect(page.getByText(/^Shopify stores · as of Oct 22, 06:00 UTC$/)).toHaveCount(2); // price, stores
  await expect(page.getByText(/^Updated-at bumps \(B, lower bound\) · Shopify stores · as of Oct 22, 00:00 UTC$/)).toBeVisible();
  await expect(canvas(page)).toBeVisible(); // the chart chunk has loaded
  await page.getByRole("group", { name: "Panes" }).getByRole("button").last().focus();
  await page.keyboard.press("Tab");
  await expect(canvas(page)).toBeFocused();
  await page.keyboard.press("End");
  const live = canvas(page).locator("xpath=following-sibling::p[@aria-live]");
  await expect(live).toContainText("Retail price: $21.90–$39.99, Shopify stores · as of Oct 22, 06:00 UTC");
  await expect(canvas(page).getByText("Stores", { exact: true })).toBeVisible(); // the tooltip
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowLeft");
  await expect(live).toContainText("Retail price: No data, Shopify stores · every run failed");
  await page.keyboard.press("Escape");
  await expect(live).toHaveText("");
});

test("search and ads have no source yet and never draw a zero line", async ({ page }) => {
  await open(page);
  await expect(missing(page).getByRole("listitem")).toHaveText([
    /Search interest· No source yetNo search keyword is linked to this product yet\./,
    /Ad count· No source yetNo ad source yet\. Ad counts arrive in Phase 8 or by CSV import\./,
  ]);
  await expect(canvas(page)).not.toHaveAttribute("aria-label", /Search interest|Ad count/);
});

test("loading shows pane skeletons", async ({ page }) => {
  await open(page, "", { hold: true });
  await expect(page.getByRole("status").filter({ hasText: "Loading trends…" })).toBeAttached();
  await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
});

test("a failed load shows the cause, the error ID and Retry", async ({ page }) => {
  await open(page, "", { status: 503 });
  await expect(page.getByRole("heading", { name: "Couldn't load the trends" })).toBeVisible();
  await expect(page.getByText("e2e-series-503").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("no history says why for every pane, with no toolbar to play with", async ({ page }) => {
  await open(page, "", { body: noHistory });
  await expect(page.getByRole("heading", { name: "No history for this product yet" })).toBeVisible();
  await expect(missing(page).getByRole("listitem")).toHaveCount(5);
  await expect(missing(page)).toContainText("Order velocity· Insufficient signal");
  await expect(page.getByRole("group", { name: "Range" })).toHaveCount(0);
  await expect(page.getByRole("tabpanel").getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");
});

test("a short history says so, and stale panes say when they were captured", async ({ page }) => {
  await open(page, "", { body: shortHistory });
  await expect(page.getByText("Only 4 days of history so far.")).toBeVisible();
  await page.unroute("**/api/v1/products/*/series*");
  await mockSeriesApi(page, { body: staleSeries });
  await page.reload();
  await expect(page.getByText(/as of Oct 19, 06:00 UTC · stale$/)).toHaveCount(3);
});

test.describe("375px", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("the toolbar wraps, the panes stack and the page never scrolls sideways", async ({ page }) => {
    await open(page);
    await expect(canvas(page)).toBeVisible();
    await page.getByRole("button", { name: "30D" }).tap();
    await expect(page).toHaveURL(`${URL}&range=30d`);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  });
});
