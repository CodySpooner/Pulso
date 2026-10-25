import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi } from "../products/fixtures";
import { FILE, mockExport, OVER_CAP } from "./export-fixtures";

// p4-09 WF-7a: Discover's Export CSV and E, against fixture feed pages and a fixture CSV (the E2E auth bypass).
const exportButton = (page: Page) => page.getByRole("button", { name: /^(Export CSV|Preparing|Downloaded)/ });
const table = (page: Page) => page.getByRole("region", { name: "Products" });
const inlineAlert = (page: Page) => page.getByRole("main").getByRole("alert"); // not Next's route announcer

test("Export CSV downloads every row of the current filters and sort", async ({ page }) => {
  await mockFeedApi(page, { items: feedItems(60), pageSize: 24 });
  const calls = await mockExport(page);
  await page.goto("/discover?view=table&sort=newest&source=cj&price_min=20");
  await expect(table(page).locator("tbody th a").first()).toBeVisible();
  const download = page.waitForEvent("download");
  await exportButton(page).click(); // 1 click
  expect((await download).suggestedFilename()).toBe(FILE);
  // The feed's query, no page cursor or size: the API streams every matching row.
  expect(calls.map((url) => url.search)).toEqual(["?sort=newest&price_min=2000&source=cj&format=csv"]);
  await expect(exportButton(page)).toHaveText("Downloaded");
  await expect(page.getByRole("status").filter({ hasText: `Downloaded ${FILE}` })).toBeAttached();
  await expect(exportButton(page)).toHaveText("Export CSV", { timeout: 5_000 });
});

test("E exports while the table or the grid has focus, not from the filters", async ({ page }) => {
  await mockFeedApi(page, { items: feedItems(20) });
  const calls = await mockExport(page);
  await page.goto("/discover?view=table");
  await expect(exportButton(page)).toHaveAttribute("aria-keyshortcuts", "E");
  await table(page).focus();
  let download = page.waitForEvent("download");
  await page.keyboard.press("e");
  expect((await download).suggestedFilename()).toBe(FILE);

  await page.getByLabel("Min price, USD").focus();
  await page.keyboard.press("e"); // typing in a filter
  await page.getByLabel("Sort", { exact: true }).focus();
  await page.keyboard.press("e");
  expect(calls).toHaveLength(1);

  await page.getByRole("button", { name: "Grid", exact: true }).click();
  await page.getByRole("list", { name: "Products" }).getByRole("link").first().focus();
  download = page.waitForEvent("download");
  await page.keyboard.press("Shift+E");
  expect((await download).suggestedFilename()).toBe(FILE);
});

test("0 rows: Export CSV is locked and says there is nothing to export", async ({ page }) => {
  await mockFeedApi(page, { items: [] });
  const calls = await mockExport(page);
  await page.goto("/discover?price_min=900");
  await expect(page.getByRole("heading", { name: "No products match this filter" })).toBeVisible();
  await expect(exportButton(page)).toHaveAttribute("aria-disabled", "true");
  await exportButton(page).focus(); // locked, still focusable, so its reason can show
  await expect(page.getByRole("tooltip")).toHaveText("Nothing to export");
  await exportButton(page).press("Enter");
  await exportButton(page).click({ force: true });
  expect(calls).toHaveLength(0);
});

test("while the API counts, Export CSV says it is preparing and takes no second press", async ({ page }) => {
  await mockFeedApi(page, { items: feedItems(12) });
  const calls = await mockExport(page, ["hold"]);
  await page.goto("/discover");
  await exportButton(page).click();
  await expect(exportButton(page)).toHaveText("Preparing export…");
  await expect(exportButton(page)).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("status").filter({ hasText: "Preparing export…" })).toBeAttached();
  await exportButton(page).click({ force: true }); // aria-disabled: Playwright would wait for it
  expect(calls).toHaveLength(1);
});

test("over the cap: the API's message inline and no file", async ({ page }) => {
  await mockFeedApi(page, { items: feedItems(12) });
  await mockExport(page, ["over-cap"]);
  await page.goto("/discover");
  let downloaded = false;
  page.on("download", () => (downloaded = true));
  await exportButton(page).click();
  await expect(inlineAlert(page)).toHaveText(OVER_CAP);
  await expect(page.getByRole("button", { name: "Retry" })).toHaveCount(0); // narrowing is the fix
  await page.getByLabel("Stores", { exact: true }).selectOption("true");
  await expect(inlineAlert(page)).toHaveCount(0); // a new query clears it
  expect(downloaded).toBe(false);
});

test("a transport failure offers Retry, which keeps focus and downloads", async ({ page }) => {
  await mockFeedApi(page, { items: feedItems(12) });
  const calls = await mockExport(page, ["down", "file"]);
  await page.goto("/discover?view=table");
  await table(page).focus();
  await page.keyboard.press("e");
  await expect(inlineAlert(page)).toContainText("Couldn't export. The Pulso API didn't answer.");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Retry" }).press("Enter");
  expect((await download).suggestedFilename()).toBe(FILE);
  await expect(exportButton(page)).toBeFocused();
  await expect(inlineAlert(page)).toHaveCount(0);
  expect(calls).toHaveLength(2);
});
