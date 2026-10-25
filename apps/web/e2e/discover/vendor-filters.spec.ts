import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi } from "../products/fixtures";
import { mockSearchApi, openPalette } from "../search/fixtures";

// imp-242: Discover's store and supplier filters, set by a palette row and shown as removable chips (DEC-300).
const chips = (page: Page) => page.getByRole("list", { name: "Store and supplier filters" });
const cards = (page: Page) => page.getByRole("list", { name: "Products" }).getByRole("article");

test("a palette store row opens Discover filtered by that store in 1 click; its chip removes the filter", async ({ page }) => {
  await mockSearchApi(page);
  const calls = await mockFeedApi(page, { items: feedItems(5) });
  const input = await openPalette(page);
  await input.fill("glowbeam");
  await page.getByRole("option", { name: /glowbeam\.example\.test/ }).click(); // the 1 click

  await expect(page).toHaveURL("/discover?store=4101");
  await expect(chips(page).getByRole("listitem")).toHaveText(["Storeglowbeam.example.test"]);
  await expect(cards(page)).toHaveCount(5);
  expect(calls.at(-1)?.searchParams.get("store")).toBe("4101");

  await chips(page).getByRole("button", { name: "Remove “Store: glowbeam.example.test”" }).click();
  await expect(page).toHaveURL("/discover");
  await expect(chips(page)).toBeHidden(); // no chip, no empty row
  await expect.poll(() => calls.at(-1)?.searchParams.has("store")).toBe(false);
});

test("keyboard only: both chips reachable with a ring; focus goes to the other chip, then to the page heading", async ({ page }) => {
  const calls = await mockFeedApi(page, { items: feedItems(5) });
  await page.goto("/discover?sort=newest&store=4101&supplier=88");
  await expect(chips(page).getByRole("listitem")).toHaveText(["Storeglowbeam.example.test", "SupplierShenzhen Glowtech Co."]);
  expect(calls.at(-1)?.search).toBe("?sort=newest&store=4101&supplier=88");
  await expect(page.getByLabel("Stores", { exact: true })).toBeVisible();

  await page.getByLabel("Stores", { exact: true }).focus(); // the last filter control, then the chips
  await page.keyboard.press("Tab");
  const removeStore = chips(page).getByRole("button", { name: "Remove “Store: glowbeam.example.test”" });
  await expect(removeStore).toBeFocused();
  await expect(removeStore).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/discover?sort=newest&supplier=88"); // sort and the other filter stay
  await expect(chips(page).getByRole("listitem")).toHaveText(["SupplierShenzhen Glowtech Co."]);
  await expect(chips(page).getByRole("button", { name: "Remove “Supplier: Shenzhen Glowtech Co.”" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/discover?sort=newest");
  await expect(page.getByRole("heading", { level: 1, name: "Discover" })).toBeFocused(); // never lost to the body
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Sort", { exact: true })).toBeFocused();
});

test("a vendor with no products: the filtered empty state names it and removes it", async ({ page }) => {
  await mockFeedApi(page, { items: [] });
  await page.goto("/discover?store=4102");
  await expect(page.getByRole("heading", { name: "No products match this filter" })).toBeVisible();
  await expect(chips(page)).toHaveText("Storenightglow.example.test");
  await page.locator("section").getByRole("button", { name: "Remove “Store: nightglow.example.test”" }).click();
  await expect(page).toHaveURL("/discover");
  await expect(page.getByRole("heading", { name: "No products collected yet" })).toBeVisible();
});

test("an unknown id reads as not found once the feed answers; while it loads the name is a skeleton", async ({ page }) => {
  await mockFeedApi(page, { items: [] });
  await page.goto("/discover?supplier=404");
  await expect(chips(page)).toHaveText("Supplier#404, not found");
  await expect(page.getByRole("heading", { name: "No products match this filter" })).toBeVisible();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockFeedApi(page, { hold: true });
  await page.goto("/discover?store=4101");
  await expect(chips(page)).toHaveText("Storeloading");
  await expect(chips(page).locator("div[aria-hidden]")).toHaveCount(1);
});

test("reduced motion: removing a chip runs no transform animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockFeedApi(page);
  await page.goto("/discover?store=4101&supplier=88");
  const list = chips(page);
  await expect(list.getByRole("listitem")).toHaveCount(2);
  // Every frame for 400 ms after the click (past spring.smooth): no chip is scaled or moved, by a WAAPI or CSS
  // animation (the global clamp leaves those ≤ 1 ms) or by Motion's frame-by-frame inline transforms.
  const sampled = list.evaluate(
    (ul) =>
      new Promise<string[]>((resolve) => {
        const seen: string[] = [];
        const end = performance.now() + 400;
        const frame = () => {
          for (const li of ul.querySelectorAll("li")) {
            const transform = getComputedStyle(li).transform;
            if (transform !== "none" && !new DOMMatrix(transform).isIdentity) seen.push(`inline ${transform}`);
          }
          for (const a of document.getAnimations()) {
            const effect = a.effect as KeyframeEffect | null;
            const inside = effect?.target instanceof Element && ul.contains(effect.target);
            const keys = (effect?.getKeyframes() ?? []).flatMap((f) => Object.keys(f));
            if (inside && Number(effect?.getComputedTiming().duration) > 1 && keys.some((k) => /transform|scale|translate/.test(k))) seen.push(`animation ${keys}`);
          }
          if (performance.now() < end) requestAnimationFrame(frame);
          else resolve(seen);
        };
        requestAnimationFrame(frame);
      }),
  );
  await list.getByRole("button", { name: /^Remove “Store/ }).click();
  expect(await sampled).toEqual([]);
  await expect(list.getByRole("listitem")).toHaveCount(1);
});

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("chips stay outside the filter sheet, count in Filters (2), and a long name never scrolls the page sideways", async ({ page }) => {
    await mockFeedApi(page);
    await page.goto("/discover?store=4101&supplier=88");
    await expect(chips(page).getByRole("listitem")).toHaveCount(2);
    await expect(page.getByRole("button", { name: "Filters (2)" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    await chips(page).getByRole("button", { name: /^Remove “Supplier/ }).tap();
    await expect(page).toHaveURL("/discover?store=4101");
  });
});
