import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi, sources } from "./fixtures";

// imp-081 (DEC-175): each sources-table row opens the CSV import panel on that source's template. A source
// without an import adapter offers a check, one without a template says why, and an open file is never
// switched to another source silently.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const COMMIT = /\/api\/v1\/admin\/sources\/[^/]+\/import$/;

async function open(page: Page) {
  await page.goto("/admin/data-health");
  const table = page.getByRole("region", { name: "Sources table" });
  const panel = page.getByRole("region", { name: "CSV import" });
  await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeVisible();
  return { table, panel };
}

const previews = (calls: { method: string; path: string }[]) => calls.filter((c) => c.path.endsWith("/import/preview")).map((c) => c.path);

test("a row opens its own template, focused on Choose CSV…, by keyboard", async ({ page }) => {
  const calls = await mockAdminApi(page);
  const { table, panel } = await open(page);

  // No import adapter: the row says "Check CSV" and why, then lands on CJ's template with the panel's reason.
  const cj = table.getByRole("button", { name: "Check CSV for CJ Dropshipping" });
  await cj.focus();
  await expect(page.getByRole("tooltip")).toHaveText("No import adapter yet: check a file against the CJ Dropshipping template now.");
  await page.keyboard.press("Enter");
  const choose = panel.getByRole("button", { name: "Choose CSV…" });
  await expect(choose).toBeFocused();
  await expect(choose).toBeInViewport();
  await expect(panel.getByLabel("Source")).toHaveValue("cj");
  await expect(panel.getByRole("link", { name: "Download template" })).toHaveAttribute("href", "/api/v1/admin/sources/cj/import/template");
  await expect(panel).toContainText("No import adapter yet");

  // Enter on Choose opens the picker; the file is checked against CJ, and Import still says why it can't.
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(file);
  await expect(panel.getByRole("status")).toHaveText(/^3 valid rows · 1 invalid row\. Importing into CJ Dropshipping arrives/);
  expect(previews(calls)).toEqual(["/v1/admin/sources/cj/import/preview"]);
});

test("by mouse, with no file open, each row switches the template at once", async ({ page }) => {
  const calls = await mockAdminApi(page);
  const { table, panel } = await open(page);
  await table.getByRole("button", { name: "Check CSV for Google Trends" }).click();
  await expect(panel.getByLabel("Source")).toHaveValue("google_trends");
  await table.getByRole("button", { name: "Import CSV for Frankfurter FX" }).click();
  await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
  await expect(panel.getByRole("link", { name: "Download template" })).toHaveAttribute("href", "/api/v1/admin/sources/fx_frankfurter/import/template");
  await expect(panel).not.toContainText("No import adapter yet");
  await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeFocused();
  expect(calls.filter((c) => c.method !== "GET")).toEqual([]); // picking a template sends nothing
});

test("a source without a template can't open the panel and says why", async ({ page }) => {
  const calls = await mockAdminApi(page, { sources: sources.map((s) => (s.key === "google_trends" ? { ...s, csv_import: null } : s)) });
  const { table, panel } = await open(page);
  const trends = table.getByRole("button", { name: "Import CSV for Google Trends" });
  await expect(trends).toHaveAttribute("aria-disabled", "true");
  await trends.focus();
  await expect(page.getByRole("tooltip")).toHaveText("No CSV template for Google Trends yet.");
  await trends.click({ force: true }); // aria-disabled: Playwright would wait for it to enable
  await expect(trends).toBeFocused();
  await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
  await expect(panel.getByLabel("Source").locator("option")).toHaveText(["Shopify stores (check only)", "CJ Dropshipping (check only)", "Frankfurter FX"]);
  expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
});

test("an open file is never switched silently: the panel asks, and Switch checks it again", async ({ page }) => {
  const calls = await mockAdminApi(page);
  const { table, panel } = await open(page);
  await panel.locator('input[type="file"]').setInputFiles(file);
  await expect(panel.getByRole("status")).toHaveText("3 valid rows · 1 invalid row");

  await table.getByRole("button", { name: "Check CSV for CJ Dropshipping" }).click();
  const switchTo = panel.getByRole("button", { name: "Switch to CJ Dropshipping" });
  await expect(switchTo).toBeFocused();
  await expect(switchTo).toHaveAccessibleDescription("rates.csv is still open for Frankfurter FX. Switching checks it against CJ Dropshipping instead.");
  // Nothing changed yet: same source, same preview, no new request.
  await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
  await expect(panel.getByRole("button", { name: "Import 3 rows" })).toBeVisible();
  expect(previews(calls)).toEqual(["/v1/admin/sources/fx_frankfurter/import/preview"]);

  // Asking for the source already open drops the question.
  await table.getByRole("button", { name: "Import CSV for Frankfurter FX" }).click();
  await expect(switchTo).toBeHidden();
  await expect(panel.getByRole("button", { name: "Choose another…" })).toBeFocused();

  await table.getByRole("button", { name: "Check CSV for CJ Dropshipping" }).click();
  await page.keyboard.press("Enter");
  await expect(panel.getByLabel("Source")).toHaveValue("cj");
  await expect(switchTo).toBeHidden();
  await expect(panel).toContainText("checked against the CJ Dropshipping template");
  expect(previews(calls)).toEqual(["/v1/admin/sources/fx_frankfurter/import/preview", "/v1/admin/sources/cj/import/preview"]);
});

test("a running import is never dropped: the panel says to wait, then shows its outcome", async ({ page }) => {
  await mockAdminApi(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(COMMIT, async (route) => {
    await held;
    await route.fallback();
  });
  const { table, panel } = await open(page);
  await panel.locator('input[type="file"]').setInputFiles(file);
  await panel.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");

  const cj = table.getByRole("button", { name: "Check CSV for CJ Dropshipping" });
  await cj.focus();
  await page.keyboard.press("Enter");
  const note = panel.getByText("rates.csv is importing into Frankfurter FX. Choose CJ Dropshipping once it finishes.");
  await expect(note).toBeFocused();
  await expect(panel.getByRole("button", { name: /^Switch to/ })).toHaveCount(0);
  await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");

  // The import lands under its own source; focus follows DEC-145 to Open runs.
  release();
  await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501/);
  await expect(note).toBeHidden();
  await expect(panel.getByRole("button", { name: "Open runs" })).toBeFocused();

  // Nothing is open now, so the row switches at once.
  await cj.click();
  await expect(panel.getByLabel("Source")).toHaveValue("cj");
  await expect(panel.getByRole("button", { name: "Choose CSV…" })).toBeFocused();
});

test("phone: the source card opens the import panel in view, without page overflow", async ({ page }) => {
  await mockAdminApi(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  await page.getByRole("button", { name: "Import CSV for Frankfurter FX" }).click();
  const choose = panel.getByRole("button", { name: "Choose CSV…" });
  await expect(choose).toBeFocused();
  await expect(choose).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
