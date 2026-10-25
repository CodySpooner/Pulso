import { expect, test, type Page } from "@playwright/test";

import { mockAmazonApi } from "./fixtures";

// AMZ-1b (DEC-286) against synthetic rank pages (the E2E auth bypass, never a database restore).
const table = (page: Page) => page.getByRole("region", { name: "Amazon ranks" });
const groups = (page: Page) => table(page).locator("tbody");
const heads = (page: Page) => groups(page).locator("th[scope=colgroup]");

test("one click from the sidebar opens every list, each rank 1 under its own category", async ({ page }) => {
  await mockAmazonApi(page);
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Amazon ranks" }).click();
  await expect(page).toHaveURL("/amazon");
  await expect(page.getByRole("main")).toContainText("Amazon · manual import, as of Oct 21, 2026 · 50 ranks in 3 lists");
  await expect(page.getByRole("main").locator("p time").first()).toHaveAttribute("title", "Imported Oct 21, 19:40 UTC");
  await expect(heads(page)).toHaveText([
    "Home & Kitchen › Best Sellers as of Oct 21, 2026 · 30 ranks",
    "Home & Kitchen › Movers & Shakers as of Oct 21, 2026 · 8 ranks",
    "Toys & Games › Best Sellers as of Oct 21, 2026 · 12 ranks",
  ]);
  for (const [i, n] of [30, 8, 12].entries()) {
    const ranks = groups(page).nth(i).locator("tr:not(:first-child) td:first-child");
    await expect(ranks).toHaveCount(n);
    await expect(ranks.first()).toHaveText("1"); // ranks restart in every list: never merged
  }
  const first = groups(page).first().locator("tr").nth(1);
  await expect(first.locator("td").first()).toHaveAttribute("title", "Amazon · manual import · as of Oct 21, 2026 · imported Oct 21, 19:40 UTC");
  await expect(first.getByRole("link")).toHaveAttribute("href", /^\/products\//);
  await expect(groups(page).first().locator("tr").nth(2).getByRole("link")).toHaveCount(0);
});

test("category and list round-trip through the URL and reach the API; a filter with no list says so", async ({ page }) => {
  const calls = await mockAmazonApi(page);
  await page.goto("/amazon");
  await page.getByLabel("Category", { exact: true }).selectOption("Toys & Games");
  await expect(page).toHaveURL("/amazon?category=Toys+%26+Games");
  await expect.poll(() => calls.at(-1)?.searchParams.get("category")).toBe("Toys & Games");
  await expect(heads(page)).toHaveCount(1);
  await page.getByLabel("List", { exact: true }).selectOption("movers");
  await expect.poll(() => calls.at(-1)?.searchParams.get("rank_kind")).toBe("movers");
  await expect(page.getByRole("heading", { name: "No Amazon list matches" })).toBeVisible();
  await page.getByRole("button", { name: "Show every list" }).click();
  await expect(page).toHaveURL("/amazon");
  await expect(heads(page)).toHaveCount(3);
  await page.goto("/amazon?kind=movers");
  await expect(page.getByLabel("List", { exact: true })).toHaveValue("movers");
  await expect(heads(page)).toHaveText(["Home & Kitchen › Movers & Shakers as of Oct 21, 2026 · 8 ranks"]);
});

test("keyboard only: Tab reaches the filters and a product link with a visible ring", async ({ page }) => {
  await mockAmazonApi(page);
  await page.goto("/amazon");
  await expect(heads(page)).toHaveCount(3);
  const category = page.getByLabel("Category", { exact: true });
  for (let i = 0; i < 60 && !(await category.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(category).toBeFocused();
  expect(await category.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  const link = table(page).getByRole("link").first();
  for (let i = 0; i < 10 && !(await link.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(link).toBeFocused();
  expect(await link.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
});

test("a long import loads more on one press", async ({ page }) => {
  await mockAmazonApi(page, { pageSize: 20 });
  await page.goto("/amazon");
  await expect(table(page).locator("tbody tr:not(:first-child)")).toHaveCount(20);
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(table(page).locator("tbody tr:not(:first-child)")).toHaveCount(40);
  await expect(page.getByText("40 of 50 loaded")).toBeVisible();
});

test.describe("states", () => {
  test("loading", async ({ page }) => {
    await mockAmazonApi(page, { hold: true });
    await page.goto("/amazon");
    await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Loading Amazon ranks…" })).toBeAttached();
  });

  test("empty: nothing imported points to the CSV import and the template", async ({ page }) => {
    await mockAmazonApi(page, { empty: true });
    await page.goto("/amazon");
    await expect(page.getByRole("heading", { name: "No Amazon import yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open CSV import" })).toHaveAttribute("href", "/admin/data-health#import");
    await expect(page.getByRole("link", { name: "Download template" })).toHaveAttribute("href", "/api/v1/admin/sources/amazon/import/template");
  });

  test("error", async ({ page }) => {
    await mockAmazonApi(page, { status: 503 });
    await page.goto("/amazon");
    await expect(page.getByRole("heading", { name: "Couldn't load Amazon ranks" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  test("stale: the newest ranks are over 14 days old", async ({ page }) => {
    await mockAmazonApi(page, { stale: true });
    await page.goto("/amazon");
    await expect(page.getByText("The newest Amazon ranks here are from Oct 5, 2026, 17 days ago.")).toBeVisible();
    await expect(heads(page)).toHaveCount(3); // an overlay on real data, never a replacement
  });

  test("no source yet: the amazon source row is missing", async ({ page }) => {
    await mockAmazonApi(page, { noSource: true });
    await page.goto("/amazon");
    await expect(page.getByRole("heading", { name: "Amazon: no source yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");
  });
});
