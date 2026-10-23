import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-077 (imp-055 follow-up): an API error in the CSV import panel carries Copy error ID, reachable by
// keyboard after Retry, and the ID stays on one line at phone width. A transport error has no ID to copy.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const REQUEST_ID = "3f2b8c1e-7d4a-4e9b-9c5f-1a2b3c4d5e6f"; // the API's default uuid4 form
const HINT = "The clipboard isn’t available here.\nSelect the ID to copy it.";
const problem503 = {
  type: "about:blank", title: "Service Unavailable", status: 503, code: "unavailable",
  detail: "The API is restarting. Try again in a minute.", request_id: REQUEST_ID, errors: [],
};

/** Checks a file, then imports it from the keyboard into a 503. Returns the panel. */
async function failImport(page: Page) {
  await mockAdminApi(page);
  await page.route(/\/sources\/[^/]+\/import$/, (route) => route.fulfill({ status: 503, json: problem503 }));
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await panel.locator('input[type="file"]').setInputFiles(file);
  await panel.getByRole("button", { name: "Import 3 rows" }).focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("alert")).toHaveText("The API is restarting. Try again in a minute. Select Retry to try again.");
  return panel;
}

async function expectRing(control: Locator) {
  await expect(control).toBeFocused();
  expect(await control.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
}

test("Tab reaches Copy error ID after Retry and copies the exact ID, unbroken at 375px", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.setViewportSize({ width: 375, height: 812 });
  const panel = await failImport(page);

  await page.keyboard.press("Tab");
  await expect(panel.getByRole("region", { name: "Row errors" })).toBeFocused(); // the preview's scrollable table
  await page.keyboard.press("Tab");
  await expectRing(panel.getByRole("button", { name: "Retry" }));
  await page.keyboard.press("Tab");
  const copy = panel.getByRole("button", { name: /^(Copy error ID|Copied)/ }); // the name follows the label
  await expectRing(copy);
  await page.keyboard.press("Enter");
  await expect(copy).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(REQUEST_ID);
  await expect(panel.getByRole("alert")).toHaveText(/^The API is restarting\. Try again in a minute\. Select Retry/); // spoken once, as before

  // One line box for the ID's text (an inline-block has one rect even when its text wraps inside it).
  const idLines = await panel.getByText(REQUEST_ID, { exact: true }).evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
  });
  expect(idLines).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test("a denied copy points at the ID, which one click selects", async ({ page }) => {
  await page.addInitScript(() => {
    navigator.clipboard.writeText = () => Promise.reject(new DOMException("Write permission denied.", "NotAllowedError"));
  });
  const panel = await failImport(page);
  const copy = panel.getByRole("button", { name: /^(Copy error ID|Couldn’t copy)/ });
  await copy.click();
  await expect(copy).toHaveAccessibleDescription(HINT);
  await panel.getByText(REQUEST_ID, { exact: true }).click();
  expect(await page.evaluate(() => getSelection()?.toString())).toBe(REQUEST_ID);
});

test("a transport error has no error ID and no Copy control", async ({ page }) => {
  await mockAdminApi(page);
  await page.route(/\/import\/preview$/, (route) => route.abort("connectionrefused"));
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await panel.locator('input[type="file"]').setInputFiles(file);
  await expect(panel.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(panel.getByText("Error ID")).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Copy error ID" })).toHaveCount(0);
});
