import { expect, test, type Locator, type Page } from "@playwright/test";

import { contrastMisses } from "../p2-39/screens";
import { mockFeedApi, PRODUCT_ID } from "../products/fixtures";
import { mockProfitApi } from "../products/profit-fixtures";
import { mockSettingsApi } from "../settings/fixtures";

// imp-313 (p2-39 B1, B2): a segmented control's pressed option carries a 2 px --segment-mark bar, the state the card
// thumb alone showed at 1.07:1; and Profit keeps its last answer at full contrast while a recompute is out. The token
// ratios themselves are in src/styles/contrast.test.ts.

/** The ::before bar of a pressed thumb, and --segment-mark resolved to rgb() for comparison. */
const mark = (thumb: Locator) =>
  thumb.evaluate((el) => {
    const bar = getComputedStyle(el, "::before");
    const probe = document.createElement("i");
    probe.style.backgroundColor = "var(--segment-mark)";
    document.body.append(probe);
    const token = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return { colour: bar.backgroundColor, token, height: bar.height, painted: bar.content !== "none" };
  });

async function expectMarked(thumb: Locator) {
  const bar = await mark(thumb);
  expect(bar.painted).toBe(true);
  expect(bar.colour).toBe(bar.token);
  expect(bar.height).toBe("2px");
}

test("Discover's view toggle marks the pressed view with the bar, and the mark follows V", async ({ page }) => {
  await mockFeedApi(page);
  await page.goto("/discover?view=table");
  const group = page.getByRole("group", { name: "View, V switches" });
  await expect(page.getByRole("region", { name: "Products" }).getByRole("row").nth(1)).toBeVisible();
  await expectMarked(group.getByRole("button", { name: "Table", pressed: true }).locator(".segment-thumb"));
  await page.keyboard.press("v");
  await expect(group.getByRole("button", { name: "Grid", pressed: true })).toBeVisible();
  await expectMarked(group.getByRole("button", { name: "Grid" }).locator(".segment-thumb"));
  await expect(group.getByRole("button", { name: "Table" }).locator(".segment-thumb")).toHaveCount(0);
});

test("Settings' duty selector marks the checked option with the bar, and only that one", async ({ page }) => {
  await mockSettingsApi(page);
  await page.goto("/settings");
  const options = page.getByRole("group", { name: "Duty", exact: true }).locator("label");
  await expect(options).toHaveCount(2);
  const checked = options.filter({ has: page.locator("input:checked") });
  await expectMarked(checked);
  expect((await mark(options.filter({ has: page.locator("input:not(:checked)") }))).painted).toBe(false);
  await options.filter({ has: page.locator("input:not(:checked)") }).click();
  await expect(checked).toHaveCount(1);
  await expectMarked(checked);
});

async function holdRecompute(page: Page) {
  await mockProfitApi(page, { holdRecompute: true });
  await page.goto(`/products/${PRODUCT_ID}?tab=profit`);
  const results = page.getByRole("tabpanel").locator("dl").first();
  await expect(results).toContainText("Profit per order▲+$0.03");
  await page.getByRole("slider", { name: "Sell price", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tabpanel").locator("[aria-busy=true]")).toHaveCount(2); // results and breakdown, until the answer lands
  return results;
}

for (const theme of ["dark", "light"] as const)
  test(`Profit keeps the last answer at full contrast while a recompute is out (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    const results = await holdRecompute(page);
    await expect(results).toContainText("Profit per order▲+$0.03"); // the old answer stays until the new one lands
    await page.waitForTimeout(300); // the theme transition settles
    for (const busy of await page.getByRole("tabpanel").locator("[aria-busy=true]").all()) expect(await busy.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
    expect(await page.evaluate(contrastMisses, "main")).toEqual([]);
  });
