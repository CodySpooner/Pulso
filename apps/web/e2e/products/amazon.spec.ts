import { expect, test, type Page } from "@playwright/test";

import { mockProductAmazonApi, noImport, noSource, notRanked, staleRanks, type AmazonRanksMock } from "./amazon-fixtures";
import { mockProductApi, PRODUCT_ID } from "./fixtures";

// p3-07 (AMZ-1c) the Trends tab's Amazon ranks section against fixture answers (the E2E auth bypass, never a database
// restore): ranks per list with the label and day, and every state.
const URL = `/products/${PRODUCT_ID}?tab=trends`;
const section = (page: Page) => page.getByRole("region", { name: "Amazon ranks" });
const lists = (page: Page) => section(page).getByRole("table").locator("tbody tr");

async function open(page: Page, options: AmazonRanksMock = {}) {
  await mockProductApi(page);
  const calls = await mockProductAmazonApi(page, options);
  await page.goto(URL);
  return calls;
}

test("a ranked product shows each list's rank and day, labelled manual import with its date", async ({ page }) => {
  await open(page);
  await expect(section(page).getByText("Amazon · manual import, as of Oct 21, 2026")).toBeVisible();
  await expect(section(page).locator("header time")).toHaveAttribute("title", "Imported Oct 21, 19:40 UTC");
  await expect(lists(page)).toHaveText([
    "Home & Kitchen › Best Sellers12Oct 21, 2026",
    "Home & Kitchen › Movers & Shakers3Oct 21, 2026",
    "Office Products › Best Sellers1,048Oct 18, 2026",
  ]);
  // Every number names its source, day and import on hover.
  await expect(lists(page).first().getByRole("cell").first()).toHaveAttribute("title", "Amazon · manual import · as of Oct 21, 2026 · imported Oct 21, 19:40 UTC · ASIN B0EX000412");
  await expect(section(page).getByText(/stale|days ago/)).toHaveCount(0);
});

test("one click opens every Amazon list", async ({ page }) => {
  await open(page);
  await section(page).getByRole("link", { name: "Every Amazon list" }).click();
  await expect(page).toHaveURL("/amazon");
});

test("a product no imported row links to reads as not ranked", async ({ page }) => {
  await open(page, { body: notRanked });
  await expect(section(page).getByText("Not in an imported Amazon list.")).toBeVisible();
  await expect(section(page).getByRole("link", { name: "Open CSV import" })).toHaveAttribute("href", "/admin/data-health#import");
  await expect(section(page).getByRole("table")).toHaveCount(0);
});

test("no import yet and no source row each say what's missing and link the next step", async ({ page }) => {
  await open(page, { body: noImport });
  await expect(section(page).getByText("No Amazon import yet.")).toBeVisible();
  await expect(section(page).getByRole("link", { name: "Open CSV import" })).toHaveAttribute("href", "/admin/data-health#import");
  await mockProductAmazonApi(page, { body: noSource });
  await page.reload();
  await expect(section(page).getByText("Amazon: no source yet.")).toBeVisible();
  await expect(section(page).getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");
});

test("stale ranks say how old they are and still show", async ({ page }) => {
  await open(page, { body: staleRanks });
  await expect(section(page).getByText("The newest Amazon ranks here are from Oct 5, 2026, 17 days ago.")).toBeVisible();
  await expect(lists(page)).toHaveText(["Home & Kitchen › Best Sellers27Oct 5, 2026"]);
});

test("an error offers Retry, which loads the ranks", async ({ page }) => {
  await open(page, { status: 503 });
  await expect(section(page).getByText("Couldn't load Amazon ranks")).toBeVisible();
  const calls = await mockProductAmazonApi(page); // the API is back
  await section(page).getByRole("button", { name: "Retry" }).click();
  await expect(lists(page)).toHaveCount(3);
  expect(calls.n).toBe(1);
});

test("loading shows a skeleton named for screen readers", async ({ page }) => {
  await open(page, { hold: true });
  await expect(section(page).getByLabel("Loading Amazon ranks")).toHaveAttribute("aria-busy", "true");
});

test("keyboard only: Tab reaches the section's link with a visible ring", async ({ page }) => {
  await open(page);
  await expect(lists(page)).toHaveCount(3);
  const link = section(page).getByRole("link", { name: "Every Amazon list" });
  for (let i = 0; i < 150 && !(await link.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(link).toBeFocused();
  expect(await link.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
});

test("no horizontal page scroll at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await open(page);
  await expect(lists(page)).toHaveCount(3);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});
