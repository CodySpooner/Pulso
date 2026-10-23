import { expect, test, type Page } from "@playwright/test";

import type { components } from "../../src/lib/api/schema";

import { cjPreview, mockAdminApi } from "./fixtures";

type S = components["schemas"];

// imp-080: the preview shows the API's parsed sample (first 20 valid rows) with no extra click, apart from
// the counts and after the row errors. Fixtures only.
const file = { name: "cj.csv", mimeType: "text/csv", buffer: Buffer.from("name,unit_cost\nLamp,5.00\n") };
const CJ_COLUMNS = ["cj_product_id", "sku", "name", "unit_cost", "currency", "warehouse_country", "ship_cost_us", "min_days", "max_days", "moq", "observed_for"];

async function checkCj(page: Page, preview: S["ImportPreview"] | (() => S["ImportPreview"])) {
  await page.route(/\/import\/preview$/, (route) => route.fulfill({ json: typeof preview === "function" ? preview() : preview }));
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await panel.getByLabel("Source").selectOption("cj");
  await panel.locator('input[type="file"]').setInputFiles(file); // the one action: choosing the file
  return panel;
}

test("the first 20 of 1,284 valid rows show as parsed, in template order, after the row errors", async ({ page }) => {
  await mockAdminApi(page);
  const panel = await checkCj(page, cjPreview);
  const sample = panel.getByRole("region", { name: "Valid rows · first 20 of 1,284" });
  await expect(sample).toBeVisible();
  await expect(sample.getByRole("columnheader")).toHaveText(CJ_COLUMNS);
  await expect(sample.getByRole("row")).toHaveCount(21);

  // Parsed values as the API sent them; a blank optional cell is "—" with its reason, never empty or 0.
  const first = sample.getByRole("row").nth(1).getByRole("cell");
  await expect(first.nth(0)).toHaveText("CJ-1000");
  await expect(first.nth(1)).toHaveAccessibleName("Blank in this row");
  await expect(first.nth(1).locator("[title]")).toHaveAttribute("title", "Blank in this row");
  await expect(first.nth(3)).toHaveText("4.50");
  await expect(first.nth(3)).toHaveCSS("text-align", "right");
  await expect(first.nth(9)).toHaveAccessibleName("Blank in this row");
  await expect(sample.getByRole("row").nth(5).getByRole("cell").nth(4)).toHaveText("EUR");

  // Markup in a value stays text.
  await expect(sample.getByRole("cell", { name: '<img src=x onerror="window.__xss=1"> Desk lamp' })).toBeVisible();
  await expect(sample.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as { __xss?: number }).__xss)).toBeUndefined();

  // Counts and errors stay separate from the sample; nothing in the sample speaks.
  await expect(panel.getByRole("button", { name: "Import 1,284 rows" })).toHaveAttribute("aria-disabled", "true");
  await expect(panel.getByRole("region", { name: "Row errors" }).getByRole("row")).toHaveCount(3);
  await expect(sample).not.toContainText("Invalid money value");
  await expect(sample.locator("[role=status], [role=alert], [aria-live]")).toHaveCount(0);
  await expect(panel.getByRole("status")).toHaveText(/^1,284 valid rows · 2 invalid rows · 1 blank line skipped\. Importing into CJ/);

  // Keyboard: the row errors come first (they are what to act on), then the sample with a visible ring;
  // End scrolls it to its last row.
  await panel.getByRole("button", { name: "Import 1,284 rows" }).focus();
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("region", { name: "Row errors" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(sample).toBeFocused();
  await expect(sample).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("End");
  await expect(sample.getByRole("cell", { name: "Fixture product 20" })).toBeInViewport();
});

test("one valid row, then none: the sample follows the latest check", async ({ page }) => {
  await mockAdminApi(page);
  let preview: S["ImportPreview"] = { ...cjPreview, rows: cjPreview.rows.slice(0, 1), valid: 1, invalid: 0, skipped: 0, error_count: 0, errors: [] };
  const panel = await checkCj(page, () => preview);
  const sample = panel.getByRole("region", { name: "Valid rows · 1 row" });
  await expect(sample.getByRole("row")).toHaveCount(2);
  await expect(sample.getByRole("columnheader")).toHaveText(["cj_product_id", "name", "unit_cost", "currency", "warehouse_country", "ship_cost_us", "min_days", "max_days", "observed_for"]);

  preview = { ...cjPreview, rows: [], valid: 0 };
  await panel.locator('input[type="file"]').setInputFiles(file);
  await expect(panel.getByRole("region", { name: "Row errors" })).toBeVisible();
  await expect(panel.getByRole("region", { name: /^Valid rows/ })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Import 0 rows" })).toHaveAttribute("aria-disabled", "true");
});

test("at 375px the sample scrolls inside its own box, never the page", async ({ page }) => {
  await mockAdminApi(page);
  await page.setViewportSize({ width: 375, height: 812 });
  const panel = await checkCj(page, cjPreview);
  const sample = panel.getByRole("region", { name: "Valid rows · first 20 of 1,284" });
  await expect(sample).toBeVisible();
  expect(await sample.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
