import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "./fixtures";
import { mockSuppliersApi, noPrice, stale, suppliers } from "./suppliers-fixtures";

// p2-26 (UX-6) Suppliers tab against fixture responses (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}?tab=suppliers`;
const table = (page: Page) => page.getByRole("region", { name: "Suppliers" });
const rowOf = (page: Page, name: string) => table(page).getByRole("row", { name: new RegExp(`^${name.replaceAll(".", "\\.")},`) });
const pick = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
const card = (page: Page, text: string) => page.getByRole("tooltip").filter({ hasText: text });
const profitRow = (page: Page, line: string) => page.getByRole("row", { name: new RegExp(`^${line}`) });

test("two clicks from the product page reach a supplier's profit, with that supplier's numbers", async ({ page }) => {
  const requests = await mockSuppliersApi(page);
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("tab", { name: "Suppliers" }).click(); // click 1
  await expect(page).toHaveURL(URL);
  await expect(pick(page, "Best margin")).toContainText("CJ Dropshipping");
  await expect(pick(page, "Best margin")).toContainText("▲+50.1%$15.03 per order before ads");
  await expect(pick(page, "Fastest shipping")).toContainText("Shenzhen Lamp Co.");
  await expect(pick(page, "Fastest shipping")).toContainText("3–5 dYunExpress to the US");
  await rowOf(page, "Shenzhen Lamp Co.").getByRole("button", { name: "Open Shenzhen Lamp Co. in Profit" }).click(); // click 2
  await expect(page).toHaveURL(`/products/${PRODUCT_ID}?tab=profit&supplier=88140`);
  await expect(page.getByRole("tab", { name: "Profit" })).toBeFocused();
  await expect.poll(() => requests.at(-1)).toEqual({ product_id: PRODUCT_ID, supplier_listing_id: 88140, quantity: 1, ddp: false });
  const row = suppliers.rows.find((r) => r.listing_id === 88140)!.cost;
  expect([row.goods_minor, row.freight_minor, row.landed_cost_minor]).toEqual([900, 300, 1380]);
  await expect(profitRow(page, "Unit cost")).toContainText("−$9.00");
  await expect(profitRow(page, "Freight")).toContainText("YunExpress · 3–5 days");
  await expect(profitRow(page, "Landed cost")).toContainText("−$13.80");
  await expect(page.getByText("listing you opened from Suppliers")).toBeVisible();
  // Back to the server's own pick: the parameter goes, and so does the supplier in the request.
  await page.getByRole("button", { name: "Let Pulso pick the supplier" }).click();
  await expect(page).toHaveURL(`/products/${PRODUCT_ID}?tab=profit`);
  await expect.poll(() => requests.at(-1)).toEqual({ product_id: PRODUCT_ID, quantity: 1, ddp: false });
});

test("an unquoted cheaper supplier never wins Best margin; its margin says why in words", async ({ page }) => {
  await mockSuppliersApi(page);
  await page.goto(URL);
  const cheap = rowOf(page, "Fuzhou Cheap Lights");
  await expect(cheap).toContainText("$1.00"); // the cheapest unit cost on the page…
  await expect(cheap).toContainText("Not quoted");
  await expect(cheap).not.toContainText("Best margin");
  await cheap.getByRole("button", { name: /^Margin withheld/ }).focus();
  await expect(card(page, "Freight isn't quoted")).toContainText("Freight isn't quoted for this variant to the US at 1 unit per order.");
  // A known out-of-stock row never picks, whatever its margin; the picks keep their badges.
  await expect(rowOf(page, "Glowhub Trading")).toContainText("Out of stock");
  await expect(rowOf(page, "Glowhub Trading")).not.toContainText(/Best margin|Fastest/);
  await expect(rowOf(page, "CJ Dropshipping")).toContainText("Best margin");
  await expect(rowOf(page, "Shenzhen Lamp Co.")).toContainText("Fastest");
  // Best margin first, then the incomplete row; the out-of-stock row last, whatever its margin.
  await expect(table(page).getByRole("row").nth(1)).toHaveAccessibleName(/^CJ Dropshipping,/);
  await expect(table(page).getByRole("row").nth(4)).toHaveAccessibleName("Fuzhou Cheap Lights, landed cost withheld");
  await expect(table(page).getByRole("row").last()).toHaveAccessibleName(/^Glowhub Trading,/);
});

test("every number opens its source; a number nothing backs reads No source yet", async ({ page }) => {
  await mockSuppliersApi(page);
  await page.goto(URL);
  const best = rowOf(page, "CJ Dropshipping");
  await best.getByRole("button", { name: "Unit cost: $6.20" }).focus();
  await expect(card(page, "#901877")).toContainText("CJ Dropshipping");
  await best.getByRole("button", { name: "Landed cost: $12.29" }).focus();
  await expect(card(page, "Computed by Pulso")).toContainText("Unit cost + freight + duty + customs fee.");
  await best.getByRole("button", { name: "Rating out of 5: No source yet" }).focus();
  await expect(card(page, "The source gives no rating.")).toBeVisible();
  const fast = rowOf(page, "Shenzhen Lamp Co.");
  await expect(fast).toContainText("4.7(312)");
  await expect(fast).toContainText("1.8Klifetime");
  await expect(fast).toContainText("US warehouse");
  await expect(rowOf(page, "Yiwu Brightway")).toContainText("9630 d");
  await fast.getByRole("button", { name: "+2 tiers" }).focus();
  await expect(card(page, "Bulk prices per unit")).toContainText("10+$5.90");
});

test("keyboard: rows move with j/k and Enter opens the focused supplier in Profit", async ({ page }) => {
  const requests = await mockSuppliersApi(page);
  await page.goto(URL);
  const first = table(page).getByRole("row").nth(1);
  await first.focus();
  await expect(first).toBeFocused();
  await page.keyboard.press("j");
  await expect(table(page).getByRole("row").nth(2)).toBeFocused();
  await page.keyboard.press("k");
  await expect(first).toBeFocused();
  await page.keyboard.press("j");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/products/${PRODUCT_ID}?tab=profit&supplier=88131`);
  await expect.poll(() => requests.at(-1)?.supplier_listing_id).toBe(88131);
  // Back on Suppliers, the supplier Profit uses is marked.
  await page.getByRole("tab", { name: "Suppliers" }).click();
  await expect(rowOf(page, "Yiwu Brightway")).toHaveAttribute("aria-selected", "true");
  await expect(rowOf(page, "Yiwu Brightway")).toContainText("In Profit");
});

test("no market price: margins are withheld once, in words; landed costs still compare and Fastest still picks", async ({ page }) => {
  await mockSuppliersApi(page, { body: noPrice });
  await page.goto(URL);
  const gaps = page.getByRole("region", { name: "Margins withheld" });
  await expect(gaps).toContainText("Pulso has no market price for this product yet.");
  await expect(pick(page, "Best margin")).toContainText("No supplier has complete costs. Needs a sell price");
  await expect(pick(page, "Fastest shipping")).toContainText("Shenzhen Lamp Co.");
  await expect(rowOf(page, "CJ Dropshipping")).toContainText("No market price");
  await expect(rowOf(page, "CJ Dropshipping")).toContainText("$12.29");
  await gaps.getByRole("button", { name: "Enter your price on Profit" }).click();
  await expect(page).toHaveURL(`/products/${PRODUCT_ID}?tab=profit`);
});

test("stale, empty, error and loading states", async ({ page }) => {
  await mockSuppliersApi(page, { body: stale });
  await page.goto(URL);
  await expect(page.getByText("Some supplier numbers are older than expected.")).toBeVisible();
  await expect(rowOf(page, "CJ Dropshipping")).toContainText("3d ago");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockSuppliersApi(page, { body: { ...suppliers, rows: [], picks: { best_margin: null, fastest: null }, as_of: null } });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "No supplier matched yet" })).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockSuppliersApi(page, { status: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't load suppliers" })).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockSuppliersApi(page, { hold: true });
  await page.goto(URL);
  await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
});

test("375 px: supplier cards, Open in Profit full width, no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const requests = await mockSuppliersApi(page);
  await page.goto(URL);
  const cards = page.getByRole("list", { name: "Suppliers" });
  await expect(cards.getByRole("listitem")).toHaveCount(5);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await cards.getByRole("listitem").filter({ hasText: "Fuzhou Cheap Lights" }).getByRole("button", { name: "Open Fuzhou Cheap Lights in Profit" }).click();
  await expect(page).toHaveURL(`/products/${PRODUCT_ID}?tab=profit&supplier=88150`);
  await expect.poll(() => requests.at(-1)?.supplier_listing_id).toBe(88150);
});
