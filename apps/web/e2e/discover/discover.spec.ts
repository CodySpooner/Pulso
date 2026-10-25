import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi, mockProductApi, product } from "../products/fixtures";

// UX-2 Discover against fixture feed pages (the E2E auth bypass, never a database restore).
const cards = (page: Page) => page.getByRole("list", { name: "Products" }).getByRole("article");
const table = (page: Page) => page.getByRole("region", { name: "Products" });
const rowTitles = (page: Page) => table(page).locator("tbody th a");
const select = (page: Page, label: string) => page.getByLabel(label, { exact: true });

test("grid and table show the same result set, from one request", async ({ page }) => {
  const calls = await mockFeedApi(page, { items: feedItems(20) });
  await page.goto("/discover");
  await expect(cards(page)).toHaveCount(20);
  const inGrid = await cards(page).getByRole("heading").allTextContents();
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await expect(page).toHaveURL(/\?view=table$/);
  await expect(rowTitles(page)).toHaveCount(20);
  expect(await rowTitles(page).allTextContents()).toEqual(inGrid);
  await expect(table(page).locator("table")).toHaveAttribute("aria-rowcount", "21");
  expect(calls).toHaveLength(1); // the view is not part of the query
});

test("sort and filters round-trip through the URL and reach the API", async ({ page }) => {
  const calls = await mockFeedApi(page);
  await page.goto("/discover?sort=newest&source=cj&price_min=20&first_seen_days=30");
  await expect(select(page, "Sort")).toHaveValue("newest");
  await expect(select(page, "Source")).toHaveValue("cj");
  await expect(select(page, "First seen")).toHaveValue("30");
  await expect(page.getByLabel("Min price, USD")).toHaveValue("20");
  await expect.poll(() => calls.at(-1)?.search).toBe("?sort=newest&price_min=2000&source=cj&first_seen_days=30");

  await select(page, "Sort").selectOption("fewest_sellers");
  await select(page, "Stores").selectOption("false");
  await select(page, "Category").selectOption({ label: "Home & Garden › Lighting › Lamps" });
  await page.getByLabel("Max price, USD").fill("60");
  await page.getByLabel("Max price, USD").press("Enter");
  const search = "?sort=fewest_sellers&category=7&price_min=20&price_max=60&source=cj&first_seen_days=30&has_sellers=false";
  await expect(page).toHaveURL(`/discover${search}`);
  await expect.poll(() => calls.at(-1)?.searchParams.get("price_max")).toBe("6000");
  expect(calls.at(-1)?.searchParams.get("has_sellers")).toBe("false");

  await page.reload();
  await expect(select(page, "Sort")).toHaveValue("fewest_sellers");
  await expect(select(page, "Category")).toHaveValue("7");
  await expect(select(page, "Stores")).toHaveValue("false");
  await expect(page.getByLabel("Max price, USD")).toHaveValue("60");
  await select(page, "Sort").selectOption("momentum");
  await expect(page).toHaveURL(/\?category=7&/); // the default sort leaves the URL
});

test("V toggles the view, which the viewer keeps on a clean URL", async ({ page }) => {
  await mockFeedApi(page);
  await page.goto("/discover");
  await expect(cards(page).first()).toBeVisible();
  await page.keyboard.press("v");
  await expect(page.getByRole("button", { name: "Table", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(rowTitles(page).first()).toBeVisible();
  await page.goto("/discover");
  await expect(rowTitles(page).first()).toBeVisible();
  await page.getByLabel("Min price, USD").press("v"); // typing in a box never toggles
  await expect(page.getByRole("button", { name: "Table", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Grid", exact: true }).click();
  await page.goto("/discover");
  await expect(cards(page).first()).toBeVisible();
});

test("a 10,000-row table loads by cursor as it scrolls and never animates a row", async ({ page }) => {
  test.setTimeout(120_000);
  const calls = await mockFeedApi(page, { items: feedItems(10_000), pageSize: 1000 });
  await page.goto("/discover?view=table");
  await expect(rowTitles(page).first()).toBeVisible();
  const region = table(page);
  for (let i = 0; i < 40 && calls.length < 10; i++) {
    await region.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
    await page.waitForTimeout(150);
  }
  await expect(region.locator("table")).toHaveAttribute("aria-rowcount", "10001");
  await region.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
  await expect(rowTitles(page).last()).toHaveText(feedItems(10_000).at(-1)!.title);
  expect(calls.map((u) => u.searchParams.get("cursor"))).toEqual([null, ...Array.from({ length: 9 }, (_, i) => String((i + 1) * 1000))]);
  for (const top of [123_456, 40_000, 2_000]) {
    await region.evaluate((el, y) => el.scrollTo({ top: y }), top);
    const rendered = await region.locator("tbody tr[aria-rowindex]").count();
    expect(rendered).toBeLessThan(80); // only the rows in view, plus overscan
    const animating = await region.evaluate((el) => document.getAnimations().filter((a) => el.contains((a.effect as KeyframeEffect)?.target ?? null)).length);
    expect(animating).toBe(0);
  }
});

test("keyboard only: Tab from the last filter reaches the first card, and Enter opens its product page", async ({ page }) => {
  const [first] = feedItems(1);
  await mockFeedApi(page);
  await mockProductApi(page, { body: { ...product, id: first.id, title: first.title } });
  await page.goto("/discover");
  await expect(cards(page).first()).toBeVisible();
  await select(page, "Stores").focus();
  await page.keyboard.press("Tab");
  const link = cards(page).first().getByRole("link", { name: first.title });
  await expect(link).toBeFocused();
  await expect(cards(page).first()).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/products/${first.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(first.title);
});

test("a card's numbers open their provenance; insufficient signal and no source yet read as words", async ({ page }) => {
  await mockFeedApi(page);
  await page.goto("/discover");
  const card = cards(page).nth(1);
  await card.getByRole("button", { name: /^Stores selling it/ }).focus();
  await expect(page.locator('[role="tooltip"]')).toContainText("Shopify stores");
  await expect(page.locator('[role="tooltip"]')).toContainText("Raw payload");
  const noSignal = cards(page).last(); // insufficient signal sorts last
  await expect(noSignal.getByRole("button", { name: "Velocity: Insufficient signal" })).toBeVisible();
  await expect(noSignal.getByRole("button", { name: "Best landed margin: No source yet" })).toBeVisible();
});

test("empty: nothing collected yet links Data Health; filtered empty removes a filter in one click", async ({ page }) => {
  await mockFeedApi(page, { items: [] });
  await page.goto("/discover");
  await expect(page.getByRole("heading", { name: "No products collected yet" })).toBeVisible();
  await expect(page.getByRole("main").getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");

  await page.goto("/discover?source=cj&has_sellers=false");
  await expect(page.getByRole("heading", { name: "No products match 2 filters" })).toBeVisible();
  await page.getByRole("button", { name: "Remove “Source: CJ Dropshipping”" }).click();
  await expect(page).toHaveURL("/discover?has_sellers=false");
  await expect(page.getByRole("heading", { name: "No products match this filter" })).toBeVisible();
});

test("degraded banner, gap chip and blocked-source cue; a failed next page keeps every loaded card", async ({ page }) => {
  await mockFeedApi(page, {
    items: feedItems(30),
    pageSize: 24,
    failMore: true,
    degraded: [{ source: "shopify_stores", source_name: "Shopify stores", state: "blocked", since: "2026-10-20T06:00:00Z" }],
  });
  await page.goto("/discover");
  await expect(page.getByRole("main")).toContainText("Shopify stores blocked since Oct 20, 06:00 UTC");
  await expect(cards(page).nth(3).getByText("gap", { exact: true })).toBeVisible();
  await expect(cards(page).first().getByText("source blocked")).toBeVisible();
  await cards(page).last().scrollIntoViewIfNeeded();
  await expect(page.getByRole("heading", { name: "Couldn't load more products" })).toBeVisible({ timeout: 15_000 });
  await expect(cards(page)).toHaveCount(24);
});

test("a failed first load shows the error with Retry", async ({ page }) => {
  await mockFeedApi(page, { status: 503 });
  await page.goto("/discover");
  await expect(page.getByRole("heading", { name: "Couldn't load products" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("filters move into a bottom sheet; the page never scrolls sideways, in either view", async ({ page }) => {
    await mockFeedApi(page);
    await page.goto("/discover");
    await expect(cards(page).first()).toBeVisible();
    await expect(select(page, "Source")).toBeHidden();
    await page.getByRole("button", { name: "Filters" }).tap();
    const sheet = page.getByRole("dialog", { name: "Filters" });
    await sheet.getByLabel("Source", { exact: true }).selectOption("cj");
    await sheet.getByRole("button", { name: "Show results" }).tap();
    await expect(page).toHaveURL("/discover?source=cj");
    await expect(page.getByRole("button", { name: "Filters (1)" })).toBeVisible();
    for (const view of ["grid", "table"]) {
      await page.goto(`/discover?view=${view}`);
      await expect(page.getByRole("main").getByRole(view === "grid" ? "article" : "row").first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    }
  });

  test("each number on a card is its own 44px tap target: tapping velocity opens velocity", async ({ page }) => {
    await mockFeedApi(page);
    await page.goto("/discover");
    await cards(page).first().getByRole("button", { name: /^Velocity, / }).tap(); // the momentum row below once took this tap
    await expect(page.locator('[role="tooltip"]')).toContainText("Velocity");
    await expect(page.locator('[role="tooltip"]')).not.toContainText("Momentum");
  });
});
