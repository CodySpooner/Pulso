import { expect, test, type Locator, type Page } from "@playwright/test";

import { feedItems, mockFeedApi, mockProductApi, PRODUCT_ID } from "../products/fixtures";

// imp-491 / imp-575: Discover's results and the product page's tab panel show on first paint and after a switch
// without waiting on Motion's features chunk, and at 1440 px Discover's ten table columns fit with no sideways
// scroll. Fixture responses only (the E2E auth bypass, never a database restore).
const table = (page: Page) => page.getByRole("region", { name: "Products" });
const grid = (page: Page) => page.getByRole("list", { name: "Products" });
/** Discover's keyed view wrapper around the table or the grid. */
const results = (page: Page) => table(page).or(grid(page)).locator("xpath=..");
/** What the viewer sees: the element's opacity times every ancestor's. */
const seen = (locator: Locator) =>
  locator.evaluate((el) => {
    let opacity = 1;
    for (let e: Element | null = el; e; e = e.parentElement) opacity *= Number(getComputedStyle(e).opacity);
    return opacity;
  });
/** LazyMotion's features chunk never arrives, so a fade Motion holds stays at opacity 0. `next dev` names it after
 *  the module; its async loader shares the name and is on the boot path, so only the chunk with domMax is held. */
const holdMotion = (page: Page) =>
  page.route(/motion-features_ts/, async (route) => {
    const response = await route.fetch();
    if (!(await response.text()).includes("domMax")) await route.fulfill({ response });
  });

test("Discover's table and cards show at full opacity with Motion's features never loaded", async ({ page }) => {
  await holdMotion(page);
  await mockFeedApi(page, { items: feedItems(20) });
  await page.goto("/discover?view=table", { waitUntil: "domcontentloaded" });
  await expect(table(page).locator("tbody th a").first()).toBeVisible();
  await expect.poll(() => seen(table(page)), { timeout: 1_000 }).toBe(1);

  // A view switch still fades, in CSS, and lands at full opacity.
  await page.getByRole("button", { name: "Grid", exact: true }).click();
  await expect(grid(page).getByRole("article").first()).toBeVisible();
  await expect(results(page)).toHaveCSS("animation-name", "enter");
  await expect.poll(() => seen(grid(page)), { timeout: 1_000 }).toBe(1);
  await page.keyboard.press("v");
  await expect.poll(() => seen(table(page)), { timeout: 1_000 }).toBe(1);
});

test("under reduced motion Discover's view switch doesn't fade", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockFeedApi(page, { items: feedItems(20) });
  await page.goto("/discover");
  await expect(grid(page).getByRole("article").first()).toBeVisible();
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await expect(table(page)).toBeVisible();
  // The fade is CSS, so the global reduced-motion rule cuts it to 0.01 ms.
  await expect(results(page)).toHaveCSS("animation-name", "enter");
  expect(parseFloat(await results(page).evaluate((el) => getComputedStyle(el).animationDuration))).toBeLessThan(0.001);
});

test("the product page's tab panel shows at full opacity with Motion's features never loaded", async ({ page }) => {
  await holdMotion(page);
  await mockProductApi(page);
  await page.goto(`/products/${PRODUCT_ID}`, { waitUntil: "domcontentloaded" });
  const panel = page.getByRole("tabpanel");
  await expect(panel.getByRole("heading", { name: "Where it appears" })).toBeVisible();
  await expect.poll(() => seen(panel.getByRole("heading", { name: "Where it appears" })), { timeout: 1_000 }).toBe(1);
  await page.getByRole("tab", { name: "Trends" }).click();
  await expect(panel.getByRole("group", { name: "Range" })).toBeVisible();
  await expect.poll(() => seen(panel.getByRole("group", { name: "Range" })), { timeout: 1_000 }).toBe(1);
});

const BLOCKED = [{ source: "shopify_stores", source_name: "Shopify stores", state: "blocked", since: "2026-10-20T06:00:00Z" }] as const;

for (const degraded of [[], BLOCKED])
  test(`at 1440 px every Discover column shows and the table doesn't scroll sideways${degraded.length ? ", a source blocked" : ""}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockFeedApi(page, { items: feedItems(60), degraded: [...degraded] });
    await page.goto("/discover?view=table");
    await expect(table(page).locator("tbody th a").first()).toBeVisible();
    if (degraded.length) await expect(table(page).getByText("· blocked").first()).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(table(page).locator("thead th")).toHaveText(["Product", "Price", "Velocity", "Momentum", "Trend", "Stores", "Suppliers", "Best margin", "First seen", "Freshness"]);
    const { scrollWidth, clientWidth } = await table(page).evaluate((el) => ({ scrollWidth: el.scrollWidth, clientWidth: el.clientWidth }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
