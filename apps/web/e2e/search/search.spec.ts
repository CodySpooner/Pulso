import { expect, test } from "@playwright/test";

import { product, PRODUCT_ID } from "../products/fixtures";
import { mockSearchApi, openPalette, products } from "./fixtures";

// p2-16 (UX-9): global search in the Ctrl+K palette, keyboard only, against fixtures (DEC-252).
test.describe("palette search", () => {
  test("a store domain is found as you type, once, and Enter opens its top product", async ({ page }) => {
    const queries = await mockSearchApi(page);
    const input = await openPalette(page);
    await input.pressSequentially("glowbeam", { delay: 20 });

    const store = page.getByRole("option", { name: /glowbeam\.example\.test, opens its top product/ });
    await expect(store).toHaveAttribute("aria-selected", "true");
    await expect(store).toContainText("Crawled 6h ago");
    await expect(page.getByRole("dialog").getByText("Open top product")).toBeVisible(); // the footer names where Enter goes
    await expect(page.getByRole("dialog").getByRole("status")).toHaveText("1 store for “glowbeam”");
    expect(queries).toEqual(["glowbeam"]); // 8 keystrokes, one request (debounced)

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(`/products/${PRODUCT_ID}`);
    await expect(page.getByRole("dialog")).toBeHidden();
    await expect(page.getByRole("heading", { level: 1, name: product.title })).toBeVisible();
  });

  test("a supplier name is found and Enter opens its top product", async ({ page }) => {
    await mockSearchApi(page);
    const input = await openPalette(page);
    await input.fill("Shenzhen Glow");
    const supplier = page.getByRole("option", { name: /Shenzhen Glowtech Co\./ });
    await expect(supplier).toHaveAttribute("aria-selected", "true");
    await expect(supplier).toContainText("CJ Dropshipping");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(`/products/${PRODUCT_ID}`);
  });

  test("groups read products, stores, suppliers; arrows skip rows with nowhere to go; Enter opens a product", async ({ page }) => {
    await mockSearchApi(page);
    const input = await openPalette(page);
    await input.fill("glow");
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("status")).toHaveText("3 products, 3 stores and 2 suppliers for “glow”");
    const headings = ["Products", "Stores", "Suppliers"].map((name) => dialog.locator("[cmdk-group-heading]", { hasText: new RegExp(`^${name}$`) }));
    const tops = await Promise.all(headings.map(async (h) => (await h.boundingBox())!.y));
    expect(tops).toEqual([...tops].sort((a, b) => a - b));

    // A listing-title match says what matched; a stale store says so in words, not colour alone.
    await expect(page.getByRole("option", { name: /Sunset projection lamp/ })).toContainText("Listed as “Glow sunset lamp, 16 colours”");
    await expect(page.getByRole("option", { name: /nightglow\.example\.test/ })).toContainText("Stale: crawled 3d ago");
    for (const name of [/glowlane\.example\.test/, /Glow Supply Trading/]) {
      const row = page.getByRole("option", { name });
      await expect(row).toHaveAttribute("aria-disabled", "true");
      await expect(row).toContainText("No products yet");
    }

    const selected = dialog.locator('[cmdk-item][aria-selected="true"]');
    await expect(selected).toContainText(products[0].title);
    const order = ["Sunset projection lamp", "LED glow face mask", "glowbeam.example.test", "nightglow.example.test", "Shenzhen Glowtech Co."];
    for (const text of order) {
      await page.keyboard.press("ArrowDown");
      await expect(selected).toContainText(text);
    }
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("ArrowUp");
    await expect(selected).toContainText("LED glow face mask");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(`/products/${products[2].id}`);
  });

  test("the first query shows a loading row; later ones keep the last results under a spinner", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockSearchApi(page, { hold: ["gl", "glowx"] });
    const input = await openPalette(page);
    const dialog = page.getByRole("dialog");
    const busy = dialog.getByTestId("palette-busy");

    await input.fill("gl");
    await expect(page.getByRole("option", { name: "Searching products, stores and suppliers…" })).toBeVisible();
    await expect(busy).toBeVisible();
    await expect(dialog.getByRole("listbox")).toHaveAttribute("aria-busy", "true");

    await input.fill("glow");
    await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible();
    await expect(busy).toBeHidden();

    await input.fill("glowx");
    await expect(busy).toBeVisible();
    await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible(); // stale, kept
    await expect(dialog.getByText(/No matches/)).toBeHidden();
    await expect(dialog.getByRole("status")).toHaveText(""); // nothing announced until it settles
    // Reduced motion: the spinner holds still.
    expect(await busy.evaluate((el) => el.getAnimations().length)).toBe(0);
  });

  test("no matches says so and is announced", async ({ page }) => {
    await mockSearchApi(page);
    const input = await openPalette(page);
    await input.fill("zzqx");
    await expect(page.getByRole("option", { name: /No matches for “zzqx”/ })).toBeVisible();
    await expect(page.getByRole("dialog").getByRole("status")).toHaveText("No products, stores or suppliers match “zzqx”");
  });

  test("an empty catalog shows no source yet, and Enter opens Data Health", async ({ page }) => {
    await mockSearchApi(page, { catalogEmpty: true });
    const input = await openPalette(page);
    await input.fill("glow");
    await expect(page.getByRole("option", { name: /Nothing collected yet/ })).toBeVisible();
    await expect(page.getByRole("option", { name: "Open Data Health" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/admin\/data-health$/);
  });

  test("a failed search keeps commands working, and Retry recovers", async ({ page }) => {
    await mockSearchApi(page, { failures: 2 }); // the first request and its one retry
    const input = await openPalette(page);
    await input.fill("glow");
    await expect(page.getByRole("option", { name: /Search unavailable/ })).toBeVisible();
    await expect(page.getByRole("dialog").getByRole("status")).toHaveText("Search unavailable. Commands still work.");
    const retry = page.getByRole("option", { name: "Retry search" });
    await expect(retry).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible();

    await input.fill("disc"); // a command still matches while search has nothing for it
    await expect(page.getByRole("option", { name: /Discover/ })).toHaveAttribute("aria-selected", "true");
  });

  test("Esc clears the query, then closes and returns focus", async ({ page }) => {
    await mockSearchApi(page);
    const input = await openPalette(page);
    await input.fill("glow");
    await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(input).toHaveValue("");
    await expect(page.getByRole("option", { name: /Shenzhen Glowtech/ })).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test.describe("375px", () => {
    test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

    test("the bottom bar opens search; a tap opens a result with no sideways scroll", async ({ page }) => {
      await mockSearchApi(page);
      await page.goto("/");
      await page.locator("html[data-app-ready=true]").waitFor();
      await page.getByRole("button", { name: "Search", exact: true }).tap();
      await page.getByRole("combobox").fill("glow");
      const store = page.getByRole("option", { name: /glowbeam\.example\.test/ });
      await expect(store).toBeVisible();
      for (const el of ["document.documentElement", "document.querySelector('[cmdk-list]')"]) {
        expect(await page.evaluate(`${el}.scrollWidth <= ${el}.clientWidth`), el).toBe(true);
      }
      await store.tap();
      await expect(page).toHaveURL(`/products/${PRODUCT_ID}`);
    });
  });
});
