import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, product, PRODUCT_ID, stale, TAB_LABELS, unmatched } from "./fixtures";

// UX-3 product page shell against fixture responses (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}`;
const openCard = (page: Page) => page.locator('[role="tooltip"]');
const stats = (page: Page) => page.getByRole("main").locator("dl").first();
const metrics = (page: Page) => stats(page).getByRole("button");
// Overview is built (UX-4); the other tabs still name the task that builds them.
const panelHeading = (page: Page, label: string) =>
  page.getByRole("tabpanel").getByRole("heading", { name: label === "Overview" ? "Where it appears" : `The ${label} tab arrives in Phase 2` });

// Sellers has its body (p2-11) and its own spec, sellers.spec.ts.
for (const [value, label] of Object.entries(TAB_LABELS).filter(([value]) => value !== "sellers")) {
  test(`?tab=${value} deep-links to ${label}`, async ({ page }) => {
    await mockProductApi(page);
    await page.goto(`${URL}?tab=${value}`);
    await expect(page.getByRole("tab", { name: label })).toHaveAttribute("aria-selected", "true");
    await expect(panelHeading(page, label)).toBeVisible();
  });
}

for (const value of ["bogus", "risk", "PROFIT", ""]) {
  test(`?tab=${value || "(empty)"} falls back to Overview without an error`, async ({ page }) => {
    await mockProductApi(page);
    await page.goto(`${URL}?tab=${value}`);
    await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await expect(panelHeading(page, "Overview")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(product.title);
  });
}

test("tabs activate manually; a switch replaces the URL and keeps other params", async ({ page }) => {
  await mockProductApi(page);
  await page.goto(`${URL}?supplier=99102`);
  const entries = await page.evaluate(() => history.length);
  await page.getByRole("tab", { name: "Overview" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Trends" })).toBeFocused();
  await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true"); // focus alone doesn't switch
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: "Trends" })).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(`${URL}?supplier=99102&tab=trends`);
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "Profit" })).toBeFocused(); // Radix moves roving focus a tick later
  await page.keyboard.press("Space");
  await expect(page).toHaveURL(`${URL}?supplier=99102&tab=profit`);
  await page.getByRole("tab", { name: "Overview" }).click(); // one click, back to the clean default URL
  await expect(page).toHaveURL(`${URL}?supplier=99102`);
  expect(await page.evaluate(() => history.length)).toBe(entries); // replace, so Back leaves the page
  await expect(page.getByRole("tab", { name: "Overview" })).toBeFocused();
});

test("every header number opens its provenance card by keyboard", async ({ page }) => {
  await mockProductApi(page);
  await page.goto(URL);
  const buttons = metrics(page);
  await expect(buttons).toHaveCount(4);
  await page.getByRole("heading", { level: 1 }).focus();
  const sources = ["Shopify stores", "CJ Dropshipping", "Shopify stores", "Shopify stores"];
  for (const [i, source] of sources.entries()) {
    await page.keyboard.press("Tab");
    await expect(buttons.nth(i)).toBeFocused();
    await expect(openCard(page)).toHaveCount(1);
    await expect(openCard(page)).toContainText(`Source${source}`);
    await expect(openCard(page)).toContainText(/As ofOct \d+, \d\d:\d\d UTC · \d+h ago/);
    await expect(openCard(page)).toContainText(/Raw payload#\d+/);
  }
  await page.keyboard.press("Escape");
  await expect(openCard(page)).toHaveCount(0);
});

test.describe("375px touch", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("every header number opens its card by tap; the page never scrolls sideways", async ({ page }) => {
    await mockProductApi(page);
    await page.goto(`${URL}?tab=profit`);
    await expect(page.getByRole("tab", { name: "Profit" })).toBeInViewport(); // the deep-linked tab scrolled into the bar
    const buttons = metrics(page);
    await expect(buttons).toHaveCount(4);
    for (let i = 0; i < 4; i++) {
      await buttons.nth(i).tap();
      await expect(openCard(page)).toHaveCount(1);
      await expect(openCard(page)).toContainText(/Source(Shopify stores|CJ Dropshipping)/);
      await expect(openCard(page)).toContainText("UTC");
      await buttons.nth(i).tap(); // a second tap keeps it open (DEC-232)
      await expect(openCard(page)).toHaveCount(1);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  });
});

test("a product with no source says so, never 0", async ({ page }) => {
  await mockProductApi(page, { body: unmatched });
  await page.goto(URL);
  const strip = stats(page);
  await expect(strip.getByRole("button", { name: /: No source yet$/ })).toHaveCount(3);
  await expect(strip).toContainText("No store listing matched yet.");
  await expect(strip).not.toContainText(/\b0\b|\$0/);
  await expect(page.getByText("Uncategorised")).toBeVisible();
  await strip.getByRole("button").first().focus();
  await expect(openCard(page)).toContainText("No source yet. No store listing matched yet.");
});

test("stale numbers say so and link to Data Health", async ({ page }) => {
  await mockProductApi(page, { body: stale });
  await page.goto(URL);
  await expect(page.getByText("Some numbers are older than expected.")).toBeVisible();
  await expect(page.getByText(/Shopify stores last captured Oct \d+, \d\d:\d\d UTC \(3d ago\)/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");
  await expect(stats(page).getByText(/· stale$/)).toHaveCount(2);
});

test("an unknown id shows not found at once", async ({ page }) => {
  const calls = await mockProductApi(page, { status: 404 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { level: 1, name: "Product not found" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No product has this ID" })).toBeVisible();
  expect(calls).toHaveLength(1); // a 4xx is not retried
});

test("a failed load shows the cause, the error ID and Retry", async ({ page }) => {
  await mockProductApi(page, { status: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't load this product" })).toBeVisible();
  await expect(page.getByText("e2e-product-503").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("a merged id shows the survivor's URL with the query string kept", async ({ page }) => {
  const survivor = "9b1d2c3e-4f50-4617-8a9b-0c1d2e3f4a5b";
  await mockProductApi(page, { body: { ...product, id: survivor } }); // fetch followed the API's 308
  await page.goto(`${URL}?tab=profit`);
  await expect(page).toHaveURL(`/products/${survivor}?tab=profit`);
  await expect(page.getByRole("tab", { name: "Profit" })).toHaveAttribute("aria-selected", "true");
});
