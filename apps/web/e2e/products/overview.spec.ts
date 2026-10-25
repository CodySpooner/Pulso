import { expect, test, type Page } from "@playwright/test";

import { firstRun, mockSettingsApi } from "../settings/fixtures";
import { mockProductApi, overviewNoDuty, overviewNoPrice, overviewNoSettings, overviewStale, overviewUnmatched, PRODUCT_ID } from "./fixtures";

// UX-4: the Overview tab and the context rail, against fixture responses (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}`;
const grid = (page: Page) => page.locator('section[aria-labelledby="key-stats"] dl');
const appears = (page: Page) => page.getByRole("region", { name: "Where it appears" });
const openCard = (page: Page) => page.locator('[role="tooltip"]');

test("the five Phase 2 stats show, each traced; the score cards stay hidden", async ({ page }) => {
  await mockProductApi(page);
  await page.goto(URL);
  await expect(grid(page).locator("dt")).toHaveText(["Price range", "Best supplier cost", "Landed margin", "First seen", "Velocity 7d"]);
  await expect(page.getByRole("tabpanel")).not.toContainText(/Trend Score|Saturation|Lifecycle/);
  const text = grid(page);
  await expect(text).toContainText("$24.00–$39.99");
  await expect(text).toContainText("Median $29.99");
  await expect(text).toContainText("$8.12");
  await expect(text).toContainText("Lowest in-stock unit cost · CJ");
  await expect(text).toContainText("$11.8839.6% margin · before adsCJ Dropshipping · 9h ago");
  await expect(text).toContainText(/Oct 13, 2026\s*9 days ago/);
  await expect(text).toContainText("34/7dGrade A");
  await expect(text).toContainText("▲ +0.47 momentum");

  // Every number is a Metric: by keyboard, each opens its card with source, as-of and raw payload, or its reason.
  const numbers = grid(page).getByRole("button");
  await expect(numbers).toHaveCount(8);
  await numbers.first().focus();
  for (let i = 0; i < 8; i++) {
    if (i) await page.keyboard.press("Tab");
    await expect(numbers.nth(i)).toBeFocused();
    await expect(openCard(page)).toHaveCount(1);
    const name = await numbers.nth(i).getAttribute("aria-label");
    await expect(openCard(page)).toContainText(/Source(Shopify stores|CJ Dropshipping)As of.*UTC/);
    if (name === "Landed margin: $11.88") await expect(openCard(page)).toContainText("MethodEstimate · Landed cost, default scenario");
  }
  await expect(numbers.first()).toHaveCSS("font-variant-numeric", "tabular-nums");
});

test("the landed margin shows Discover's answer, or what it still needs", async ({ page }) => {
  // imp-280: one look on the default tab, no click. Its hover names the oldest input's source and as-of.
  await mockProductApi(page);
  await page.goto(URL);
  const margin = grid(page).getByRole("button", { name: "Landed margin: $11.88" });
  await margin.hover();
  await expect(openCard(page)).toContainText(/SourceCJ DropshippingAs of.*UTC · 9h ago/);
  await expect(openCard(page)).toContainText("Raw payload#901903");

  // Incomplete: the gap R-16 withholds it for. Duty, the one Settings closes, reads amber and in words.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { overview: overviewNoDuty });
  await page.goto(URL);
  const noDuty = grid(page).getByRole("button", { name: "Landed margin: Duty not set" });
  await expect(noDuty).toHaveClass(/text-warning/);
  await expect(grid(page)).toContainText("Duty not setNeeds a duty rate.");
  await noDuty.focus();
  await expect(openCard(page)).toContainText("Duty not set. Needs a duty rate.");

  // No supplier pick and no market price: no number, never $0, and every missing input named.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { overview: overviewUnmatched });
  await page.goto(URL);
  await expect(grid(page).getByRole("button", { name: "Landed margin: No source yet" })).toBeVisible();
  await expect(grid(page)).toContainText("Needs a market price, a supplier price and a freight quote.");
});

test("each withheld margin's one next action lands on its fix in one click", async ({ page }) => {
  // imp-368: duty opens Settings with the rate box open and focused, ready to type.
  await mockProductApi(page, { overview: overviewNoDuty });
  await mockSettingsApi(page, { settings: firstRun });
  await page.goto(URL);
  await grid(page).getByRole("link", { name: "Set duty" }).click();
  await expect(page).toHaveURL("/settings#duty");
  await expect(page.getByRole("radio", { name: "Set a rate" })).toBeChecked();
  await expect(page.getByRole("textbox", { name: /^Default duty rate/ })).toBeFocused();

  // No supplier or quote: Suppliers, by keyboard from the margin's number, with focus on the tab it opened.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { overview: overviewUnmatched });
  await page.goto(URL);
  await grid(page).getByRole("button", { name: "Landed margin: No source yet" }).focus();
  await page.keyboard.press("Tab");
  const suppliers = grid(page).getByRole("button", { name: "Open Suppliers" });
  await expect(suppliers).toBeFocused();
  await expect(suppliers).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`${URL}?tab=suppliers`);
  await expect(page.getByRole("tab", { name: "Suppliers" })).toBeFocused();

  // Only the price is missing: Profit, where the sell price is typed.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { overview: overviewNoPrice });
  await page.goto(URL);
  await grid(page).getByRole("button", { name: "Enter a price" }).click();
  await expect(page).toHaveURL(`${URL}?tab=profit`);
  await expect(page.getByRole("tab", { name: "Profit" })).toBeFocused();

  // No settings row yet: Settings, whose first read creates it.
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { overview: overviewNoSettings });
  await mockSettingsApi(page, { settings: firstRun });
  await page.goto(URL);
  await grid(page).getByRole("link", { name: "Open Settings" }).click();
  await expect(page).toHaveURL("/settings");
  await expect(page.getByRole("heading", { name: "Duty default" })).toBeVisible();
});

test("where it appears counts per source and opens the Suppliers and Sellers tabs", async ({ page }) => {
  await mockProductApi(page);
  await page.goto(URL);
  const rows = appears(page).getByRole("listitem");
  await expect(rows).toHaveText([/^SuppliersCJ Dropshipping3Suppliers$/, /^StoresShopify stores12Sellers$/, /^AdsNo ad source is connected yet\.No source yet$/]);
  // Counts sit right-aligned in their column, in tabular numerals.
  const three = rows.nth(0).getByRole("button", { name: "Suppliers on CJ Dropshipping: 3" });
  await expect(three).toHaveCSS("justify-self", "flex-end");
  await expect(three).toHaveCSS("font-variant-numeric", "tabular-nums");
  await page.getByRole("button", { name: "Open the Suppliers tab" }).click(); // one click
  await expect(page).toHaveURL(`${URL}?tab=suppliers`);
  await expect(page.getByRole("tab", { name: "Suppliers" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Suppliers" })).toBeFocused(); // focus lands on the tab it opened
  await page.getByRole("tab", { name: "Overview" }).click();
  await page.getByRole("button", { name: "Open the Sellers tab" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`${URL}?tab=sellers`);
  await expect(page.getByRole("tab", { name: "Sellers" })).toBeFocused();
});

test("a product with no source says so, never 0", async ({ page }) => {
  await mockProductApi(page, { overview: overviewUnmatched });
  await page.goto(URL);
  await expect(grid(page).getByRole("button", { name: /: No source yet$/ })).toHaveCount(4);
  await expect(grid(page).getByRole("button", { name: "Velocity 7d: Insufficient signal" })).toBeVisible();
  await expect(grid(page)).toContainText("No in-stock supplier offer yet.");
  await expect(appears(page).getByRole("button", { name: /: No source yet$/ })).toHaveCount(3);
  await expect(appears(page).getByRole("listitem")).toHaveText([
    "SuppliersNo supplier listing matched yet.No source yetSuppliers",
    "StoresNo store listing matched yet.No source yetSellers",
    "AdsNo ad source is connected yet.No source yet",
  ]);
  await expect(page.getByRole("tabpanel")).not.toContainText(/\$0|\b0\b/);
});

test("loading shows the card skeleton, an error the cause with Retry; the header stays", async ({ page }) => {
  await mockProductApi(page, { holdOverview: true });
  await page.goto(URL);
  await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
  await expect(appears(page)).toHaveCount(0);

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { overviewStatus: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't load the overview" })).toBeVisible();
  await expect(page.getByText("e2e-overview-503").first()).toBeVisible();
  await expect(page.getByRole("tabpanel").getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Sunset projection lamp/);
});

test("stale retail numbers say so on their card", async ({ page }) => {
  await mockProductApi(page, { overview: overviewStale });
  await page.goto(URL);
  await expect(grid(page).getByText("Shopify stores · 3d ago · stale")).toBeVisible();
});

test.describe("375px touch", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("the overview fits without sideways scroll; a tap opens a card", async ({ page }) => {
    await mockProductApi(page);
    await page.goto(URL);
    await expect(appears(page)).toBeVisible();
    await grid(page).getByRole("button", { name: "Best supplier cost: $8.12" }).tap();
    await expect(openCard(page)).toContainText("SourceCJ Dropshipping");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(375);
  });
});
