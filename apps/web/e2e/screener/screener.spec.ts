import { expect, test, type Page } from "@playwright/test";

import { contrastMisses } from "../p2-39/screens";
import { mockResultPage, mockScreenerApi, NULL_TREND, rows, savedScreen, screenerRow } from "./fixtures";

// p4-32 (WF-1b) Screener against fixture responses under the E2E auth bypass, never a database restore.
const table = (page: Page) => page.getByRole("region", { name: "Products" });
const links = (page: Page) => table(page).locator("tbody th a");
const filters = (page: Page) => page.getByRole("region", { name: "Filters" });
const screenButton = (page: Page) => page.getByRole("button", { name: /^Screen/ });
const tip = (page: Page) => page.locator('[role="tooltip"]:not([data-state="closed"])');
const sent = (calls: URL[]) => {
  const url = calls.at(-1)!;
  return { filters: JSON.parse(url.searchParams.get("filters")!), sort: url.searchParams.get("sort"), order: url.searchParams.get("order") };
};

test("keyboard only: build a two-condition screen, run it, sort it, save it and open a result", async ({ page }) => {
  const api = await mockScreenerApi(page);
  await mockResultPage(page, 0);
  await page.goto("/screener");
  await expect(links(page).first()).toBeVisible();
  let keys = 0;
  const press = async (...seq: string[]) => {
    for (const key of seq) await page.keyboard.press(key);
    keys += seq.length;
  };
  const type = async (text: string) => {
    await page.keyboard.type(text);
    keys += text.length;
  };

  await press("f", "Enter"); // Add filter, its first metric (highlighted): Landed margin
  await expect(page.getByLabel("Landed margin, at least (%)")).toBeFocused();
  await type("40");
  await press("Enter"); // runs the screen
  await expect.poll(() => sent(api.calls).filters).toEqual({ margin_bps_min: 4000 });
  await press("Tab", "Tab", "Enter", "Enter"); // past Max to Add filter; its first metric: Lifecycle
  await expect(filters(page).getByRole("button", { name: "Emerging" })).toBeFocused();
  await press("Space", "Tab", "Space");
  await expect.poll(() => sent(api.calls).filters).toEqual({ margin_bps_min: 4000, lifecycle: ["emerging", "rising"] });
  await press("Tab", "Tab", "Tab", "Tab", "Tab"); // the other stages, Add filter, then Sort
  await expect(page.getByLabel("Sort", { exact: true })).toBeFocused();
  await press("ArrowDown");
  await expect.poll(() => sent(api.calls).sort).toBe("opportunity");

  await press("Control+s");
  await expect(page.getByRole("dialog", { name: "Save screen" })).toBeVisible();
  await type("Early");
  await press("Enter");
  await expect(screenButton(page)).toContainText("Early");
  await expect(page).toHaveURL(/\?screen=[0-9a-f-]{36}$/);
  expect([...api.screens.values()][0]).toMatchObject({ name: "Early", filters: { margin_bps_min: 4000, lifecycle: ["emerging", "rising"] }, sort: "opportunity" });

  await expect(page.getByLabel("Sort", { exact: true })).toBeFocused(); // focus came back from the dialog
  await press("Tab", "Tab", "Tab", "Tab", "Tab"); // order, Columns, Export CSV, the table, its first product
  await expect(links(page).first()).toBeFocused();
  await press("Enter");
  await expect(page).toHaveURL(`/products/${screenerRow(0).id}`);
  console.log(`p4-32 keyboard flow: ${keys} keys, 0 clicks`);
  expect(keys).toBeLessThanOrEqual(31);
});

test("an unsaved screen round-trips through the URL: reload gives the same screen and request", async ({ page }) => {
  const api = await mockScreenerApi(page);
  await page.goto("/screener");
  await filters(page).getByRole("button", { name: "Ships to US in ≤ 10 days" }).click(); // a first-visit example
  await page.getByLabel("Sort", { exact: true }).selectOption("price");
  await page.getByRole("button", { name: "Order: highest first" }).click();
  await page.getByRole("button", { name: "Columns" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Supplier rating" }).click();
  await page.keyboard.press("Escape");
  await expect(table(page).getByRole("columnheader", { name: "Supplier rating" })).toBeVisible();
  const before = sent(api.calls);
  expect(before).toEqual({ filters: { ship_days_us_max: 10 }, sort: "price", order: "asc" });
  const url = page.url();
  expect(new URL(url).searchParams.get("q")).toMatch(/^[\w-]+$/);

  await page.reload();
  await expect(links(page).first()).toBeVisible();
  expect(page.url()).toBe(url);
  expect(sent(api.calls)).toEqual(before);
  await expect(page.getByLabel("Ship days to US, at most (days)")).toHaveValue("10");
  await expect(page.getByLabel("Sort", { exact: true })).toHaveValue("price");
  await expect(page.getByRole("button", { name: "Order: lowest first" })).toBeVisible();
  await expect(table(page).getByRole("columnheader", { name: "Supplier rating" })).toBeVisible();
  await expect(screenButton(page)).toContainText("Unsaved screen");
});

test("a saved screen opens, is replaced with Save and renamed, and both persist", async ({ page }) => {
  const screen = savedScreen();
  const api = await mockScreenerApi(page, { screens: [screen] });
  await page.goto(`/screener?screen=${screen.id}`);
  await expect(screenButton(page)).toContainText("Early & profitable");
  await expect(page.getByLabel("Landed margin, at least (%)")).toHaveValue("40");
  await expect.poll(() => sent(api.calls)).toEqual({ filters: screen.filters, sort: "margin_bps", order: "desc" });
  await expect(page.getByRole("button", { name: /^Saved/ })).toBeDisabled();

  const min = page.getByLabel("Landed margin, at least (%)");
  await min.fill("35");
  await min.press("Enter");
  await expect(screenButton(page)).toContainText("unsaved changes");
  await expect(page).toHaveURL(new RegExp(`screen=${screen.id}&q=`));
  await page.getByRole("button", { name: /^Save/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved “Early & profitable”" })).toBeVisible();
  await expect(page).toHaveURL(`/screener?screen=${screen.id}`);
  expect(api.screens.get(screen.id)?.filters?.margin_bps_min).toBe(3500);

  await page.getByRole("button", { name: "More screen actions" }).click();
  await page.getByRole("menuitem", { name: "Rename…" }).click();
  await page.getByLabel("Screen name").fill("Morning screen");
  await page.keyboard.press("Enter");
  await expect(screenButton(page)).toContainText("Morning screen");

  await page.reload();
  await expect(screenButton(page)).toContainText("Morning screen");
  await expect(page.getByLabel("Landed margin, at least (%)")).toHaveValue("35");
  await expect(screenButton(page)).not.toContainText("unsaved changes");
});

test("a taken name says so; duplicate opens the copy; delete can be undone", async ({ page }) => {
  const screen = savedScreen();
  const api = await mockScreenerApi(page, { screens: [screen, savedScreen({ id: "6d1f8a2b-3c4e-4f60-9bac-1d2e3f4a5b6c", name: "Taken" })] });
  await page.goto(`/screener?screen=${screen.id}`);
  await expect(screenButton(page)).toContainText("Early & profitable");
  await page.getByRole("button", { name: "More screen actions" }).click();
  await page.getByRole("menuitem", { name: "Save as new…" }).click();
  await page.getByLabel("Screen name").fill("Taken");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toHaveText("You already have a screen named “Taken”.");
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "More screen actions" }).click();
  await page.getByRole("menuitem", { name: "Duplicate" }).click();
  await expect(screenButton(page)).toContainText("Early & profitable copy");
  expect(api.screens.size).toBe(3);

  await page.getByRole("button", { name: "More screen actions" }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Deleted “Early & profitable copy”" })).toBeVisible();
  await expect(screenButton(page)).toContainText("Unsaved screen");
  await expect(page.getByLabel("Landed margin, at least (%)")).toHaveValue("40"); // the screen's results stay
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(screenButton(page)).toContainText("Early & profitable copy");
  expect([...api.screens.values()].map((s) => s.name).sort()).toEqual(["Early & profitable", "Early & profitable copy", "Taken"]);
});

test("a NULL Trend reads insufficient signal with its reason; no score row reads no source yet, never 0", async ({ page }) => {
  await mockScreenerApi(page);
  await page.goto("/screener");
  const [nullRow, noRow] = [table(page).getByRole("row").nth(1), table(page).getByRole("row").nth(2)];
  const trend = nullRow.getByRole("button", { name: /^Trend:/ });
  await expect(trend).toHaveText("Trend: Insufficient signal");
  await trend.focus();
  await expect(tip(page)).toContainText(`Insufficient signal. ${NULL_TREND}`);
  await expect(tip(page)).toContainText("the UTC day scored");
  await expect(noRow.getByRole("button", { name: /^Trend:/ })).toHaveText("Trend: No source yet");
  await expect(noRow.getByRole("button", { name: /^Lifecycle:/ })).toHaveText("Lifecycle: No source yet");
  await expect(noRow.getByRole("button", { name: /^Saturation:/ })).toHaveText("Saturation: No source yet");
  await expect(noRow.getByRole("button", { name: /^Opportunity:/ })).toHaveText("Opportunity: Insufficient signal");
  const scored = table(page).getByRole("row").nth(3).getByRole("button", { name: /^Trend:/ });
  await expect(scored).toHaveText(`Trend: ${92 - 2 * 3}`);
  await scored.focus();
  await expect(tip(page)).toContainText("Pulso model v0.1.0");
});

test("risk is visible but disabled until Phase 5", async ({ page }) => {
  await mockScreenerApi(page);
  await page.goto("/screener");
  await page.getByRole("button", { name: "Add filter" }).click();
  const risk = page.getByRole("menuitem", { name: /Risk/ });
  await expect(risk).toContainText("Phase 5");
  await expect(risk).toHaveAttribute("aria-disabled", "true");
});

test("no matches offers to remove each condition; an error keeps the screen and retries", async ({ page }) => {
  const options = { empty: true, status: 503 as number | undefined };
  await mockScreenerApi(page, options);
  await page.goto(`/screener?q=${btoa(JSON.stringify({ filters: { margin_bps_min: 9000 } })).replace(/=+$/, "")}`);
  await expect(page.getByRole("heading", { name: "Couldn't run this screen" })).toBeVisible();
  options.status = undefined;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "No products match" })).toBeVisible();
  await page.getByRole("button", { name: "Remove “Landed margin ≥ 90%”" }).click();
  await expect(page.getByLabel("Landed margin, at least (%)")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "No products collected yet" })).toBeVisible();
});

test("keyset Load more appends the next page; 375px shows two-line rows with no horizontal scroll", async ({ page }) => {
  const api = await mockScreenerApi(page, { items: rows(60) });
  await page.goto("/screener");
  await expect(table(page).locator("table")).toHaveAttribute("aria-rowcount", "51");
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(table(page).locator("table")).toHaveAttribute("aria-rowcount", "61");
  expect(api.calls.map((u) => u.searchParams.get("cursor"))).toEqual([null, "50"]);

  await page.setViewportSize({ width: 375, height: 812 });
  const cards = page.getByRole("list", { name: "Products" }).getByRole("article");
  await expect(cards).toHaveCount(60);
  await expect(cards.first().getByRole("button")).toHaveCount(3); // the first three columns
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.getByRole("button", { name: "Filters" }).click();
  await expect(page.getByRole("dialog", { name: "Filters" }).getByRole("button", { name: "Add filter" })).toBeVisible();
});

for (const theme of ["dark", "light"] as const)
  test(`every text run keeps AA contrast, with a saved screen open and its tooltip shown (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    const screen = savedScreen({ filters: { margin_bps_min: 4000, lifecycle: ["emerging", "rising"], ship_days_us_max: 10 } });
    await mockScreenerApi(page, { screens: [screen] });
    await page.goto(`/screener?screen=${screen.id}`);
    await expect(links(page).first()).toBeVisible();
    await page.getByLabel("Ship days to US, at most (days)").fill("12"); // unsaved: the dot and the primary Save
    await page.getByLabel("Ship days to US, at most (days)").press("Enter");
    await table(page).getByRole("row").nth(1).getByRole("button", { name: /^Trend:/ }).focus();
    await page.waitForTimeout(300);
    expect(await page.evaluate(contrastMisses, "main")).toEqual([]);
    expect(await page.evaluate(contrastMisses, '[role="tooltip"]')).toEqual([]);
  });

test("Export CSV and E download every matching row in the screen's filters and sort", async ({ page }) => {
  const api = await mockScreenerApi(page);
  const q = btoa(JSON.stringify({ filters: { margin_bps_min: 4000 }, sort: "price", order: "asc" })).replace(/=+$/, "");
  await page.goto(`/screener?q=${q}`);
  await expect(links(page).first()).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toBe("pulso_screener_2026-10-22.csv");
  const csv = api.calls.filter((u) => u.searchParams.get("format") === "csv");
  expect(csv).toHaveLength(1);
  expect(sent(csv)).toEqual({ filters: { margin_bps_min: 4000 }, sort: "price", order: "asc" });
  expect(csv[0].searchParams.has("cursor")).toBe(false);

  await links(page).first().focus();
  const again = page.waitForEvent("download");
  await page.keyboard.press("e"); // from the results
  await again;
  await page.getByLabel("Landed margin, at least (%)").press("e"); // typing never exports
  expect(api.calls.filter((u) => u.searchParams.get("format") === "csv")).toHaveLength(2);
});
