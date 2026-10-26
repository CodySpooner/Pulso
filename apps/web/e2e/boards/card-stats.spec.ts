import { expect, test, type Page } from "@playwright/test";

import { BOARD, mockBoardsApi, SURVIVOR } from "./fixtures";

// imp-454: each card's five stats, traced on hover and focus, "No source yet" per stat (never 0), and the merged
// note, against fixture responses (the E2E auth bypass, never a database restore).
const Q4 = `/boards/${BOARD(1)}`;
const tooltip = (page: Page) => page.locator('[role="tooltip"]:not([data-state="closed"])');
const stat = (page: Page, product: string, name: string) => page.getByRole("article", { name: product }).getByRole("button", { name, exact: true });

test("a grid card shows its price range, best margin, Trend, Lifecycle and Saturation, each traced on focus", async ({ page }) => {
  await mockBoardsApi(page);
  await page.goto(Q4);
  for (const name of ["Lowest retail price: $24.99", "Highest retail price: $34.99", "Best landed margin: $11.82 · 47.3%", "Trend Score: 78", "Lifecycle stage: Rising", "Saturation: 34"])
    await expect(stat(page, "Sunset projection lamp", name)).toBeVisible();

  await stat(page, "Sunset projection lamp", "Trend Score: 78").focus();
  await expect(tooltip(page)).toContainText("Pulso score · 001-scores-2a1c9e");
  await expect(tooltip(page)).toContainText("As of");
  await stat(page, "Sunset projection lamp", "Lowest retail price: $24.99").focus();
  await expect(tooltip(page)).toContainText("Shopify stores");
  await stat(page, "Sunset projection lamp", "Best landed margin: $11.82 · 47.3%").focus();
  await expect(tooltip(page)).toContainText("CJdropshipping");
});

test("a stat nothing backs reads No source yet or Insufficient signal, never 0, and says why", async ({ page }) => {
  await mockBoardsApi(page);
  await page.goto(Q4);
  for (const name of ["Retail price: No source yet", "Best landed margin: No source yet", "Trend Score: No source yet", "Lifecycle stage: No source yet", "Saturation: No source yet"])
    await expect(stat(page, "Posture corrector brace", name)).toBeVisible();
  await expect(page.getByRole("article", { name: "Posture corrector brace" }).getByText(/\$0|^0$/)).toHaveCount(0);
  await stat(page, "Posture corrector brace", "Trend Score: No source yet").focus();
  await expect(tooltip(page)).toContainText("nothing has scored this product");

  await stat(page, "Cloud pillow slides", "Trend Score: Insufficient signal").focus();
  await expect(tooltip(page)).toContainText("Insufficient signal: every input missing.");
  await expect(stat(page, "Mini waffle maker", "Best landed margin: −$3.39 · −14.7%")).toBeVisible(); // a loss, U+2212
  await expect(page.getByRole("article", { name: "Mini waffle maker" }).getByText("· stale")).toBeVisible();
});

test("a merged card says so and links to the product it became", async ({ page }) => {
  await mockBoardsApi(page);
  await page.goto(Q4);
  const merged = page.getByRole("article", { name: "Cloud pillow slides" });
  await expect(merged.getByText("Merged into another product; its stats show here.")).toBeVisible();
  await expect(merged.getByRole("link", { name: /Open it/ })).toHaveAttribute("href", `/products/${SURVIVOR}`);
  await expect(page.getByRole("article", { name: "Sunset projection lamp" }).getByText(/Merged/)).toHaveCount(0);
});

test("the table shows the same stats, numbers right-aligned, and keyboard focus reaches each", async ({ page }) => {
  await mockBoardsApi(page);
  await page.goto(`${Q4}?view=table`);
  const header = page.getByRole("columnheader");
  await expect(header).toHaveText(["Selected", "Reorder", "#", "Product", "Price", "Best margin", "Trend", "Lifecycle", "Saturation", "Note", "Data as of", "Added", "Actions"]);
  const row = page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: "Galaxy star projector" }) });
  await expect(row.getByRole("button", { name: "Lifecycle stage: Emerging" })).toBeVisible();
  for (const name of ["Price", "Best margin", "Trend", "Saturation"]) await expect(header.filter({ hasText: name })).toHaveCSS("text-align", "right");
  await row.getByRole("button", { name: "Trend Score: 65" }).focus();
  await expect(tooltip(page)).toContainText("001-scores-2a1c9e");
  await expect(page.getByRole("row").filter({ hasText: "Cloud pillow slides" }).getByRole("link", { name: /Open it/ })).toBeVisible();
});

for (const [width, view] of [
  [1440, "grid"],
  [1440, "table"],
  [375, "grid"],
  [375, "table"],
] as const)
  test(`stats render at ${width}px in the ${view} with no horizontal page scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockBoardsApi(page);
    await page.goto(view === "table" ? `${Q4}?view=table` : Q4);
    await expect(page.getByRole("button", { name: "Lifecycle stage: Rising" }).first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
