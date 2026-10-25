import { expect, test, type Page } from "@playwright/test";

import { brandRule, CATEGORIES, LATEST, mockPopularApi } from "./fixtures";

// P2-29 b (DEC-272) and the brand list (DEC-277) against synthetic report pages (the E2E auth bypass, never a database
// restore).
const table = (page: Page) => page.getByRole("region", { name: "Google popular products" });
const rows = (page: Page) => table(page).locator("tbody tr");
const toggle = (page: Page) => page.getByRole("button", { name: /^Show hidden brands/ });

test("one click from the sidebar opens the newest week with big brands hidden", async ({ page }) => {
  await mockPopularApi(page);
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Google popular" }).click();
  await expect(page).toHaveURL("/google-popular");
  await expect(rows(page)).toHaveCount(30);
  await expect(page.getByLabel("Week", { exact: true })).toHaveValue(LATEST);
  await expect(page.getByLabel("Category", { exact: true })).toHaveValue(CATEGORIES[0]);
  await expect(page.getByRole("main")).toContainText("30 products, 10 from major brands hidden · Google Merchant Center Popular products, as of the week of Oct 19, 2026");
  await expect(toggle(page)).toHaveAccessibleName("Show hidden brands (10)");
  // Signed change with a glyph, "New" in words, and a linked and an unlinked title.
  const first = rows(page).first();
  await expect(first.locator("td").nth(1)).toHaveText("▲+3 places");
  await expect(rows(page).nth(2).locator("td").nth(1)).toHaveText("New");
  await expect(first.getByRole("link")).toHaveAttribute("href", /^\/products\//);
  await expect(rows(page).nth(1).getByRole("link")).toHaveCount(0);
  await expect(page.getByText("internal use only")).toBeVisible();
});

test("keyboard only: Tab reaches the toggle with a visible ring, and one Enter shows hidden brands", async ({ page }) => {
  const calls = await mockPopularApi(page);
  await page.goto("/google-popular");
  await expect(rows(page)).toHaveCount(30);
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("Tab");
    if (await toggle(page).evaluate((el) => el === document.activeElement)) break;
  }
  await expect(toggle(page)).toBeFocused();
  expect(await toggle(page).evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "true");
  await expect(rows(page)).toHaveCount(40);
  await expect(page).toHaveURL("/google-popular?brands=all");
  expect(calls.at(-1)?.searchParams.get("include_major_brands")).toBe("true");
  await expect(rows(page).nth(3)).toContainText("Major");
  await expect(toggle(page)).toBeFocused(); // the toolbar stays while the report reloads
});

test("week and category round-trip through the URL and reach the API", async ({ page }) => {
  const calls = await mockPopularApi(page);
  await page.goto("/google-popular");
  await page.getByLabel("Category", { exact: true }).selectOption(CATEGORIES[1]);
  await expect(page).toHaveURL(`/google-popular?category=${encodeURIComponent(CATEGORIES[1]).replaceAll("%20", "+")}`);
  await expect.poll(() => calls.at(-1)?.searchParams.get("category")).toBe(CATEGORIES[1]);
  await page.getByLabel("Week", { exact: true }).selectOption("2026-10-12");
  await expect.poll(() => calls.at(-1)?.searchParams.get("week")).toBe("2026-10-12");
  expect(calls.at(-1)?.searchParams.get("category")).toBe(CATEGORIES[1]); // a new week keeps the category
});

test("a long report loads more on one press", async ({ page }) => {
  await mockPopularApi(page, { rows: 300, pageSize: 200 });
  await page.goto("/google-popular?brands=all");
  await expect(rows(page)).toHaveCount(200);
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(rows(page)).toHaveCount(300);
  await expect(page.getByText("300 of 300 loaded")).toBeVisible();
});

test.describe("states", () => {
  test("loading", async ({ page }) => {
    await mockPopularApi(page, { hold: true });
    await page.goto("/google-popular");
    await expect(page.locator(".bg-skeleton:visible").first()).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "Loading Google popular products…" })).toBeAttached();
  });

  test("empty: nothing imported points to the CSV import", async ({ page }) => {
    await mockPopularApi(page, { empty: true });
    await page.goto("/google-popular");
    await expect(page.getByRole("heading", { name: "No Google popular report yet" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open CSV import" })).toHaveAttribute("href", "/admin/data-health#import");
  });

  test("error", async ({ page }) => {
    await mockPopularApi(page, { status: 503 });
    await page.goto("/google-popular");
    await expect(page.getByRole("heading", { name: "Couldn't load Google popular products" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });

  test("stale: the newest report is over 14 days old", async ({ page }) => {
    await mockPopularApi(page, { stale: true });
    await page.goto("/google-popular");
    await expect(page.getByText("The newest report is for the week of Oct 5, 2026, 17 days ago.")).toBeVisible();
    await expect(rows(page).first()).toBeVisible(); // an overlay on real data, never a replacement
  });

  test("no source yet: no earlier week to compare", async ({ page }) => {
    await mockPopularApi(page, { noPrevious: true });
    await page.goto("/google-popular");
    await expect(page.getByText("Weekly change: no source yet.")).toBeVisible();
    await expect(rows(page).first().locator("td").nth(1)).toHaveText("—No source yet: the week of Oct 12, 2026 isn't imported");
  });
});

test.describe("brand list (DEC-277)", () => {
  const action = (page: Page, name: string) => table(page).getByRole("button", { name }).first();
  const panel = (page: Page) => page.getByRole("dialog", { name: "Your brands" });
  const manage = (page: Page) => page.getByRole("button", { name: "Manage brands" });

  test("one click hides a brand for the workspace, and Undo brings it back", async ({ page }) => {
    const rules = new Map();
    await mockPopularApi(page, { rules });
    await page.goto("/google-popular");
    await expect(rows(page)).toHaveCount(30);
    await action(page, "Hide brand Kestrelle").click(); // the only click
    await expect(rows(page)).toHaveCount(25);
    await expect(table(page)).not.toContainText("Kestrelle");
    expect(rules.get("kestrelle")?.action).toBe("hide");
    await expect(page.getByRole("main")).toContainText("25 products, 15 hidden: 10 from major brands, 5 by you");
    await expect(toggle(page)).toHaveAccessibleName("Show hidden brands (15)");
    await page.getByRole("status").filter({ hasText: "Kestrelle hidden" }).getByRole("button", { name: "Undo" }).click();
    await expect(rows(page)).toHaveCount(30);
    expect(rules.has("kestrelle")).toBe(false);
    await expect(page.getByRole("status").filter({ hasText: "Kestrelle unhidden" })).toBeVisible();
  });

  test("Manage brands unhides in two clicks, and a shown major brand stays with a chip", async ({ page }) => {
    const rules = new Map([
      ["ordwell", brandRule("Ordwell", "hide")],
      ["vantoro", brandRule("Vantoro", "show")],
    ]);
    await mockPopularApi(page, { rules });
    await page.goto("/google-popular");
    await expect(rows(page)).toHaveCount(35); // Ordwell's 5 rows hidden; Vantoro's 10 shown despite the 10-row rule
    await expect(rows(page).filter({ hasText: "Vantoro" }).first()).toContainText("Shown");
    await manage(page).click(); // click 1
    await expect(panel(page).getByRole("region", { name: "Hidden brands" })).toContainText("Ordwell");
    await expect(panel(page).getByRole("region", { name: "Always shown brands" })).toContainText("Vantoro");
    await panel(page).getByRole("button", { name: "Unhide Ordwell" }).click(); // click 2
    await expect(rows(page)).toHaveCount(40);
    expect(rules.has("ordwell")).toBe(false);
    await expect(panel(page).getByRole("button", { name: "Stop showing Vantoro" })).toBeFocused(); // focus stays in the list
    await page.keyboard.press("Enter");
    await expect(panel(page).getByText("No hidden brands yet")).toBeVisible();
    await expect(rows(page)).toHaveCount(30);
  });

  test("keyboard only: Tab reaches a row's Hide brand with a visible ring, Enter hides, focus moves to the next row", async ({ page }) => {
    await mockPopularApi(page);
    await page.goto("/google-popular");
    await expect(rows(page)).toHaveCount(30);
    const first = action(page, "Hide brand Kestrelle");
    for (let i = 0; i < 80; i++) {
      await page.keyboard.press("Tab");
      if (await first.evaluate((el) => el === document.activeElement)) break;
    }
    await expect(first).toBeFocused();
    await expect(first).toHaveCSS("opacity", "1");
    expect(await first.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
    await page.keyboard.press("Enter");
    await expect(rows(page)).toHaveCount(25);
    await expect(action(page, "Hide brand Ordwell")).toBeFocused();
  });

  test("with hidden brands shown, a major brand is one click from always shown", async ({ page }) => {
    const rules = new Map();
    await mockPopularApi(page, { rules });
    await page.goto("/google-popular?brands=all");
    await expect(rows(page)).toHaveCount(40);
    await expect(rows(page).nth(3)).toContainText("Major");
    await action(page, "Always show brand Vantoro").click();
    await expect(rows(page).nth(3)).toContainText("Shown");
    expect(rules.get("vantoro")?.action).toBe("show");
    await toggle(page).click();
    await expect(rows(page)).toHaveCount(40); // nothing left to hide
  });

  test("a failed change puts the rows back and says why", async ({ page }) => {
    await mockPopularApi(page, { writeStatus: 503 });
    await page.goto("/google-popular");
    await action(page, "Hide brand Kestrelle").click();
    await expect(page.getByRole("status").filter({ hasText: "Couldn't change Kestrelle: The API is restarting. Try again." })).toBeVisible();
    await expect(rows(page)).toHaveCount(30);
  });

  test.describe("Manage brands states", () => {
    test("loading", async ({ page }) => {
      await mockPopularApi(page, { brandsHold: true });
      await page.goto("/google-popular");
      await manage(page).click();
      await expect(panel(page).locator(".bg-skeleton").first()).toBeVisible();
      await expect(panel(page).getByRole("status")).toHaveText("Loading your brands…");
    });

    test("empty", async ({ page }) => {
      await mockPopularApi(page);
      await page.goto("/google-popular");
      await manage(page).click();
      await expect(panel(page).getByText("No hidden brands yet")).toBeVisible();
    });

    test("error", async ({ page }) => {
      await mockPopularApi(page, { brandsStatus: 503 });
      await page.goto("/google-popular");
      await manage(page).click();
      await expect(panel(page).getByRole("heading", { name: "Couldn't load your brands" })).toBeVisible({ timeout: 15_000 });
      await expect(panel(page).getByRole("button", { name: "Retry" })).toBeVisible();
    });
  });
});
