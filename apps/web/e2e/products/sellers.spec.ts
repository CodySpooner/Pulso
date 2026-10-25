import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "./fixtures";
import { empty, mockSellersApi, paused } from "./sellers-fixtures";

// p2-11 (UX-7) Sellers tab against fixture responses (the E2E auth bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}?tab=sellers`;
const table = (page: Page) => page.getByRole("region", { name: "Sellers" });
const rowOf = (page: Page, domain: string) => table(page).getByRole("row", { name: new RegExp(`^${domain.replaceAll(".", "\\.")},`) });
const chip = (page: Page, name: string) => page.getByRole("button", { name, exact: true });

test("two clicks from the product page reach delisted sellers, each with its date; Unknown says why", async ({ page }) => {
  const calls = await mockSellersApi(page);
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("tab", { name: "Sellers" }).click();
  await expect(page).toHaveURL(URL);
  await expect(rowOf(page, "trendyglow.com")).toContainText("Listed");
  await expect(rowOf(page, "bright-nest.com")).toHaveCount(0); // Active only by default
  await chip(page, "Include delisted").click();
  await expect(page).toHaveURL(`${URL}&sellers=all`);
  await expect(rowOf(page, "bright-nest.com")).toContainText("Delisted Oct 18");
  expect(calls.at(-1)).toContain("include_delisted=true");
  await expect(rowOf(page, "homeglow.co")).toContainText("Delisted Oct 10");
  // A partial last crawl reads Unknown, never Delisted, and the reason opens by keyboard.
  const unknown = rowOf(page, "cozycorner.shop").getByRole("button", { name: "Unknown" });
  await unknown.focus();
  await expect(page.locator('[role="tooltip"]')).toContainText("Only a complete crawl marks a listing delisted");
  await expect(rowOf(page, "cozycorner.shop")).not.toContainText("Delisted");
});

test("the started basis, conversion, no-USD row and ads column say what they are", async ({ page }) => {
  await mockSellersApi(page);
  await page.goto(URL);
  await expect(rowOf(page, "trendyglow.com")).toContainText("store date");
  await expect(rowOf(page, "trendyglow.com")).toContainText("from$24.00");
  await expect(rowOf(page, "glowupgoods.com")).toContainText("first seen");
  await expect(rowOf(page, "lumenhaus.co")).toContainText("$32.85CAD");
  await expect(rowOf(page, "moodlight.eu")).toContainText("€29.00 no USD rate");
  await expect(rowOf(page, "trendyglow.com")).toContainText("No source yet");
  await expect(rowOf(page, "trendyglow.com")).not.toContainText(/\bNo\b(?! source)/);
  await expect(page.getByText(/leaves out untrackable stores/)).toBeVisible();
});

test("the summary shows the active-only spread, the counts and a band that needs landed cost", async ({ page }) => {
  await mockSellersApi(page);
  await page.goto(URL);
  await expect(page.getByRole("region", { name: "Price spread" }).getByText("$24.00–$39.99")).toBeVisible();
  await expect(page.getByText("median $29.99 · mean $30.96")).toBeVisible();
  await expect(page.getByRole("img", { name: "5 active sellers from $24.00 to $39.99" })).toBeVisible();
  await expect(page.getByText("1 new in 14 d · 2 delisted in 30 d")).toBeVisible();
  await expect(page.getByRole("img", { name: /Active sellers per day over 90 days, 39 days observed/ })).toBeVisible();
  const band = page.getByRole("region", { name: "Suggested price" });
  await expect(band).toContainText("No source yet");
  await expect(band).toContainText("won't suggest a price from the market alone");
  await expect(band).not.toContainText("$");
});

test("F cycles the chips in the URL; j/k move rows; filtered empty offers a way back", async ({ page }) => {
  await mockSellersApi(page);
  await page.goto(URL);
  await expect(rowOf(page, "trendyglow.com")).toBeVisible();
  await page.keyboard.press("f");
  await expect(page).toHaveURL(`${URL}&sellers=all`);
  await page.keyboard.press("f");
  await expect(page).toHaveURL(`${URL}&sellers=new`);
  await expect(table(page).getByRole("row")).toHaveCount(2); // header + nightsky
  await page.keyboard.press("f");
  await expect(chip(page, "Tracked only")).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("f");
  await expect(page).toHaveURL(URL);
  await expect(table(page).getByRole("row")).toHaveCount(8); // the active rows replace the kept Tracked only page
  const first = table(page).getByRole("row").nth(1);
  await first.focus();
  await page.keyboard.press("j");
  await expect(table(page).getByRole("row").nth(2)).toBeFocused();
  await page.keyboard.press("k");
  await expect(first).toBeFocused();
});

test("the crawler banner shows whenever the store crawler is off", async ({ page }) => {
  await mockSellersApi(page, { body: paused });
  await page.goto(URL);
  await expect(page.getByRole("status").filter({ hasText: "Store crawler stopped itself" })).toContainText("repeated blocks, HTTP 429");
});

test("empty state", async ({ page }) => {
  await mockSellersApi(page, { body: empty });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "No stores seen selling this yet" })).toBeVisible();
  await expect(page.getByText("No USD price from an active seller yet.")).toBeVisible();
});

test("error state", async ({ page }) => {
  await mockSellersApi(page, { status: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't load sellers" })).toBeVisible();
});

test("loading state", async ({ page }) => {
  await mockSellersApi(page, { hold: true });
  await page.goto(URL);
  await expect(page.getByRole("tabpanel").locator(".bg-skeleton").first()).toBeVisible();
});

test("375 px: seller cards, delisted folded into a group, no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockSellersApi(page);
  await page.goto(`${URL}&sellers=all`);
  const cards = page.getByRole("list", { name: "Sellers" });
  await expect(cards.getByRole("listitem")).toHaveCount(7);
  const group = page.getByText("Delisted (2)");
  await expect(group).toBeVisible();
  await expect(page.getByRole("link", { name: "bright-nest.com" })).toBeHidden();
  await group.click();
  await expect(page.getByRole("link", { name: "bright-nest.com" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
});
