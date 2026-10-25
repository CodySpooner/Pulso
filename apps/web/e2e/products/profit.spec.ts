import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "./fixtures";
import { complete, incomplete, mockProfitApi, noFreight, noPrice, noSupplier, stale } from "./profit-fixtures";

// p2-20 (UX-8 part b) Profit tab against fixture calc answers (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}?tab=profit`;
const results = (page: Page) => page.getByRole("tabpanel").locator("dl").first();
const row = (page: Page, line: string) => page.getByRole("row", { name: new RegExp(`^${line}`) });
const slider = (page: Page, name: string) => page.getByRole("slider", { name, exact: true });
// The open card holding `text`; a closing one stays in the DOM for its exit fade.
const card = (page: Page, text: string) => page.getByRole("tooltip").filter({ hasText: text });

test("complete costs: the tab shows the endpoint's landed cost and margin, each number with its source", async ({ page }) => {
  const requests = await mockProfitApi(page);
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("tab", { name: "Profit" }).click(); // one click from the product page
  await expect(page).toHaveURL(URL);
  await expect(results(page)).toContainText("Profit per order▲+$0.03after $15.00 ad cost");
  expect(requests).toEqual([{ product_id: PRODUCT_ID, quantity: 1, ddp: false }]); // one call; the defaults are the server's
  await expect(results(page)).toContainText("Margin▲+0.1%50.1% before ads");
  await expect(results(page)).toContainText("Break-even ad cost$15.03");
  await expect(row(page, "Landed cost")).toContainText("−$12.29");
  await expect(row(page, "Landed cost")).toContainText("41.0%");
  await expect(row(page, "Profit before ads")).toContainText("$15.03");
  await expect(row(page, "Freight")).toContainText("CJPacket · 8–12 days");
  await expect(row(page, "Duty")).toContainText("20% of goods");
  await expect(row(page, "Payment fee")).toContainText("2.9% + $0.30");
  await expect(row(page, "FX")).toContainText("supplier prices in USD");
  await expect(row(page, "Sell price")).toContainText("Shopify stores · 6h ago");
  // Every amount opens its provenance by keyboard: an observation's source and raw payload, a total's formula.
  await row(page, "Unit cost").getByRole("button", { name: "Unit cost: −$6.20" }).focus();
  await expect(card(page, "#901877")).toContainText("Unit cost");
  await expect(card(page, "#901877")).toContainText("CJ Dropshipping");
  await row(page, "Landed cost").getByRole("button").focus();
  await expect(card(page, "Computed by Pulso")).toContainText("Unit cost + freight + duty + customs fee.");
  await row(page, "Ad cost").getByRole("button").focus();
  await expect(card(page, "Ad cost per order")).toContainText("Workspace settings");
});

test("moving the sell-price slider recomputes on the server; profit and margin change; Reset restores", async ({ page }) => {
  const requests = await mockProfitApi(page);
  await page.goto(URL);
  await expect(results(page)).toContainText("+$0.03");
  await slider(page, "Sell price").focus();
  await page.keyboard.press("ArrowRight");
  await expect(slider(page, "Sell price")).toHaveAttribute("aria-valuetext", "$30.49");
  await expect(results(page)).toContainText("Profit per order▲+$0.50");
  await expect(results(page)).toContainText("Margin▲+1.6%50.8% before ads");
  expect(requests.at(-1)).toEqual({ product_id: PRODUCT_ID, quantity: 1, ddp: false, price_minor: 3049 });
  await expect(page.getByRole("textbox", { name: "Sell price" })).toHaveValue("30.49");
  await expect(page.getByRole("region", { name: "Scenario" }).getByText("Your estimate")).toBeVisible();
  await page.getByRole("button", { name: "Reset to defaults" }).click();
  await expect(results(page)).toContainText("+$0.03");
  await expect(slider(page, "Sell price")).toHaveAttribute("aria-valuetext", "$29.99");
  await expect(page.getByRole("button", { name: "Reset to defaults" })).toBeDisabled();
});

test("missing freight: the reason in plain words and no margin from partial costs", async ({ page }) => {
  await mockProfitApi(page, { body: noFreight });
  await page.goto(URL);
  const banner = page.getByRole("region", { name: "Profit and margin are withheld" });
  await expect(banner).toContainText("Freight isn't quoted for this variant to the US at 1 unit per order.");
  await expect(results(page)).toContainText("Profit per orderWithheldNeeds a freight quote");
  await expect(results(page)).not.toContainText("%");
  await expect(results(page)).not.toContainText("$");
  await expect(row(page, "Freight")).toContainText("Not quoted");
  for (const line of ["Landed cost", "Profit before ads", "Profit per order"]) await expect(row(page, line)).toContainText("Withheld");
  await expect(row(page, "Unit cost")).toContainText("−$6.20"); // what is known still shows
});

test("duty not set reads in words, with the way to set it", async ({ page }) => {
  await mockProfitApi(page, { body: incomplete });
  await page.goto(URL);
  const banner = page.getByRole("region", { name: "Profit and margin are withheld" });
  await expect(banner).toContainText("2 inputs are missing:");
  await expect(banner).toContainText("Duty isn't set: Settings has no US duty rate yet, and Pulso never assumes 0%.");
  await expect(banner.getByRole("link", { name: "Set a US duty rate in Settings" })).toHaveAttribute("href", "/settings");
  await expect(row(page, "Duty")).toContainText("Not set");
});

test("keyboard only: every slider and input is reachable and operable, with a visible focus ring", async ({ page }) => {
  const requests = await mockProfitApi(page);
  await page.goto(URL);
  await expect(results(page)).toContainText("+$0.03");
  const price = page.getByRole("textbox", { name: "Sell price" });
  await page.getByRole("tab", { name: "Profit" }).focus(); // from the tab bar, Tab walks the panel in order
  for (let i = 0; i < 12 && !(await price.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(price).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(slider(page, "Sell price")).toBeFocused();
  await expect(slider(page, "Sell price")).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("End");
  await expect(slider(page, "Sell price")).toHaveAttribute("aria-valuetext", "$59.99");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("radio", { name: "1 unit" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "2 units" })).toBeFocused(); // Radix moves roving focus a tick later
  await page.keyboard.press("Space");
  await expect(page.getByRole("radio", { name: "2 units" })).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Tab");
  await expect(slider(page, "Returns")).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(slider(page, "Returns")).toHaveAttribute("aria-valuetext", "6%");
  await page.keyboard.press("Tab");
  await page.keyboard.press("ArrowLeft");
  await expect(slider(page, "Payment fee")).toHaveAttribute("aria-valuetext", "2.8%");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+ArrowRight"); // ten steps
  await expect(slider(page, "Ad cost per order")).toHaveAttribute("aria-valuetext", "$20.00");
  await expect.poll(() => requests.at(-1)).toEqual({
    product_id: PRODUCT_ID, quantity: 2, ddp: false, price_minor: 5999, returns_bps: 600, payment_fee_bps: 280, ad_cost_minor: 2000,
  });
  // Reset is reachable too: back up to it and press Enter.
  await page.getByRole("button", { name: "Reset to defaults" }).focus();
  await page.keyboard.press("Enter");
  await expect(slider(page, "Returns")).toHaveAttribute("aria-valuetext", "5%");
  await expect(page.getByRole("radio", { name: "1 unit" })).toHaveAttribute("aria-checked", "true");
});

test("no market price: the price input asks for one, and a typed price prices the order", async ({ page }) => {
  await mockProfitApi(page, { body: noPrice });
  await page.goto(URL);
  await expect(page.getByText("No market price yet: enter one")).toBeVisible();
  await expect(page.getByRole("region", { name: "Profit and margin are withheld" })).toContainText("No sell price: Pulso has no market price for it yet.");
  await expect(slider(page, "Sell price")).toHaveCount(0);
  const price = page.getByRole("textbox", { name: "Sell price" });
  await price.fill("29.999");
  await price.press("Enter");
  await expect(page.getByText("Enter a price like 29.99.")).toBeVisible();
  await price.fill("29.99");
  await price.press("Enter");
  await expect(results(page)).toContainText("+$0.03");
  await expect(slider(page, "Sell price")).toHaveAttribute("aria-valuetext", "$29.99");
});

test("no supplier: no source yet, with the CSV fallback", async ({ page }) => {
  await mockProfitApi(page, { body: noSupplier });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "No supplier cost yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Import a CSV in Data Health" })).toBeVisible();
});

test("stale inputs are named, and their lines marked", async ({ page }) => {
  await mockProfitApi(page, { body: stale });
  await page.goto(URL);
  await expect(page.getByText("Some inputs are older than expected.")).toBeVisible();
  await expect(page.getByText(/CJ Dropshipping last captured Oct 19, \d\d:00 UTC \(3d ago\)/)).toBeVisible();
  await expect(row(page, "Unit cost")).toContainText("CJ Dropshipping · 3d ago · stale");
  await expect(results(page)).toContainText("+$0.03"); // stale data stays on screen
});

test("a failed recompute keeps the last result with Retry", async ({ page }) => {
  await mockProfitApi(page, { failRecompute: true });
  await page.goto(URL);
  await expect(results(page)).toContainText("+$0.03");
  await slider(page, "Ad cost per order").focus();
  await page.keyboard.press("ArrowRight");
  const line = page.getByRole("group", { name: "Couldn't recompute this scenario" });
  await expect(line).toContainText("The API is restarting.");
  await expect(line.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(results(page)).toContainText("+$0.03");
});

test("error state", async ({ page }) => {
  await mockProfitApi(page, { status: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't calculate profit" })).toBeVisible();
});

test("loading state", async ({ page }) => {
  await mockProfitApi(page, { hold: true });
  await page.goto(URL);
  await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
});

test("375 px: sources sit under each line, no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockProfitApi(page, { body: complete });
  await page.goto(URL);
  await expect(row(page, "Sell price").getByText("Shopify stores · 6h ago").filter({ visible: true })).toHaveCount(1); // under the line
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
});
