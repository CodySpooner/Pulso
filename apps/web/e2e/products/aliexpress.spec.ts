import { expect, test, type Page } from "@playwright/test";

import { NOW } from "../data-health/fixtures";
import { empty, found, LINK, LIVE, mockAliExpressApi, paused } from "./aliexpress-fixtures";
import { PRODUCT_ID } from "./fixtures";

// p3-05 (AE-3, DEC-289): the Suppliers tab's AliExpress lookup against fixture answers (the E2E auth bypass).
const URL = `/products/${PRODUCT_ID}?tab=suppliers`;
const section = (page: Page) => page.getByRole("region", { name: "AliExpress", exact: true });
const box = (page: Page) => page.getByLabel("AliExpress product link or number");
const look = (page: Page) => section(page).getByRole("button", { name: "Look up" });

test("two clicks from the product page show its AliExpress cost, and every number carries the live, not-stored badge", async ({ page }) => {
  const posted = await mockAliExpressApi(page, [empty]);
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("tab", { name: "Suppliers" }).click(); // click 1
  await expect(section(page)).toContainText("No lookup yet");
  await box(page).fill(LINK); // a paste, not a click
  await look(page).click(); // click 2
  const variants = page.getByRole("region", { name: "AliExpress variants" });
  await expect(variants.getByRole("row", { name: /12000000000000001/ })).toContainText("$3.99");
  expect(posted).toEqual([{ link: LINK }]);
  await expect(box(page)).toHaveValue("");

  // Every row says where it came from, and every number's own name carries the badge.
  const rows = section(page).locator("tbody tr");
  await expect(rows).toHaveCount(4);
  for (const row of await rows.all()) await expect(row).toContainText(LIVE);
  const numbers = section(page).getByRole("button").filter({ hasNotText: "Look up" });
  await expect(numbers).toHaveCount(11); // rating, reviews; 3 + 2 per variant (one stock unknown); 2 per shipping option
  for (const name of await numbers.evaluateAll((els) => els.map((el) => el.getAttribute("aria-label")))) expect(name).toContain(LIVE);
  await expect(page.getByRole("region", { name: "AliExpress shipping to the US, 1 unit" })).toContainText("Fixture Standard$4.999–15 dCN");

  // Hover, focus or tap opens the number's card: the badge as its source, its as-of time, and nothing stored.
  await variants.getByRole("button", { name: `Unit cost · ${LIVE}: $3.99` }).focus();
  const card = page.getByRole("tooltip").filter({ hasText: "Unit cost" });
  await expect(card).toContainText(`Source${LIVE}`);
  await expect(card).toContainText("As ofOct 22, 12:00 UTC · 2h ago");
  await expect(card).toContainText("Raw payloadNot stored");
  await expect(section(page)).toContainText("As of Oct 22, 12:00 UTC · gone at Oct 23, 12:00 UTC");
});

test("AE-3: with the source off, the rows disappear when their 24 h cache ends", async ({ page }) => {
  const soon = { ...found, as_of: new Date(NOW.getTime() - 86_400_000 + 2_000).toISOString(), expires_at: new Date(NOW.getTime() + 2_000).toISOString() };
  await mockAliExpressApi(page, [soon, { status: "disabled" }]);
  await page.goto(URL);
  await expect(page.getByRole("region", { name: "AliExpress variants" })).toBeVisible();
  await expect(section(page).getByRole("heading", { name: "AliExpress is off: needs the owner's app approval" })).toBeVisible({ timeout: 8_000 });
  await expect(page.getByRole("region", { name: "AliExpress variants" })).toHaveCount(0);
  await expect(section(page)).not.toContainText("$3.99");
});

test("off and not configured say what the owner must do, with no link box", async ({ page }) => {
  for (const [status, why] of [
    ["disabled", "lookups start on the collector host once the owner's AliExpress app is approved"],
    ["not_configured", "this host has no AliExpress app keys"],
  ] as const) {
    await mockAliExpressApi(page, [{ status }]);
    await page.goto(URL);
    await expect(section(page).getByRole("heading", { name: "AliExpress is off: needs the owner's app approval" })).toBeVisible();
    await expect(section(page)).toContainText(why);
    await expect(section(page)).toContainText("Owner To-Dos: Start the AliExpress applications."); // <q> adds the quotes
    await expect(section(page).getByRole("link", { name: "Data Health" })).toHaveAttribute("href", "/admin/data-health");
    await expect(box(page)).toHaveCount(0);
    await page.unrouteAll();
  }
});

test("loading, error with retry, paused, and a stale refresh", async ({ page }) => {
  await mockAliExpressApi(page, ["hold"]);
  await page.goto(URL);
  await expect(section(page).getByRole("status")).toHaveText("Loading the AliExpress lookup…");
  await page.unrouteAll();

  await mockAliExpressApi(page, [503, 503, empty]); // the first load retries once
  await page.goto(URL);
  await expect(section(page).getByRole("heading", { name: "Couldn't load the AliExpress lookup" })).toBeVisible();
  await section(page).getByRole("button", { name: "Retry" }).click();
  await expect(box(page)).toBeVisible();
  await page.unrouteAll();

  await mockAliExpressApi(page, [paused]);
  await page.goto(URL);
  await expect(section(page)).toContainText("Lookups resume at Oct 22, 14:05 UTC (in 5m).");
  await expect(box(page)).toHaveCount(0);
  await page.unrouteAll();

  await mockAliExpressApi(page, [found, 503]);
  await page.goto(URL);
  await expect(page.getByRole("region", { name: "AliExpress variants" })).toBeVisible();
  await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000)); // past the 5-minute staleTime
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange"))); // the tab refocuses: a refetch
  await expect(section(page).getByRole("group", { name: "Couldn't refresh the AliExpress lookup" })).toContainText("Error ID e2e-aliexpress-503");
  await expect(page.getByRole("region", { name: "AliExpress variants" })).toContainText("$3.99"); // still inside its 24 h
});

test("by keyboard: Enter looks up; a wrong link and a lookup without an answer say why", async ({ page }) => {
  await mockAliExpressApi(page, [empty], 422);
  await page.goto(URL);
  await box(page).focus();
  await page.keyboard.type("https://example.com/item/1.html");
  await page.keyboard.press("Enter");
  await expect(section(page).getByRole("alert")).toContainText("That isn't an AliExpress product link.");
  await expect(box(page)).toHaveValue("https://example.com/item/1.html"); // nothing typed is lost
  await page.unrouteAll();

  await mockAliExpressApi(page, [empty], { status: "error" });
  await page.goto(URL);
  await box(page).focus();
  await page.keyboard.type("1005000000000001");
  await page.keyboard.press("Enter");
  await expect(section(page).getByRole("status")).toContainText("AliExpress didn't answer, so nothing was kept. Try again.");
  await page.unrouteAll();

  await mockAliExpressApi(page, [empty]);
  await page.goto(URL);
  await box(page).focus();
  await page.keyboard.type(LINK);
  await page.keyboard.press("Enter");
  const variants = page.getByRole("region", { name: "AliExpress variants" });
  await expect(variants).toBeVisible();
  await page.keyboard.press("Tab"); // the box, then Look up (disabled once empty), then the product's numbers
  await expect(section(page).getByRole("button", { name: /^Rating out of 5/ })).toBeFocused();
});
