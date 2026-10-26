import { expect, test, type Page } from "@playwright/test";

import { PRODUCT_ID } from "../products/fixtures";
import { LONG_URL, mockSearchApi, type SearchMock } from "../search/fixtures";
import { lists, mockAlertsApi, PET_LIST, ruleList } from "./fixtures";

// imp-527: New rule on the Rules tab, a product search (the palette's GET /v1/search) or a watchlist, then the
// builder; imp-585: a 422 in words. Fixture responses only (the E2E auth bypass, never a database restore).
const LAMP = "Sunset projection lamp with 16 colour modes and remote";
const list = (page: Page) => page.getByRole("region", { name: "Alert rules" });
const row = (page: Page, name: string) => list(page).getByRole("row").filter({ has: page.getByRole("rowheader", { name: new RegExp(`^${name}`) }) });

async function open(page: Page, search: SearchMock = {}) {
  const queries = await mockSearchApi(page, search);
  const api = await mockAlertsApi(page, { rules: ruleList(), lists: lists() });
  await page.goto("/alerts?view=rules");
  await page.locator("html[data-app-ready=true]").waitFor();
  return { api, queries, newRule: page.getByRole("button", { name: "New rule" }), dialog: page.getByRole("dialog"), search: page.getByRole("combobox", { name: "Product or watchlist" }) };
}

test("New rule: search a product, pick it, choose a verb and save, and it tops the list (4 clicks)", async ({ page }) => {
  const { api, newRule, dialog, search } = await open(page);
  await expect(newRule).toHaveAttribute("aria-keyshortcuts", "N");
  await newRule.click(); // 1
  await expect(page.getByRole("dialog", { name: "New alert rule" })).toBeVisible();
  await expect(search).toBeFocused();
  await expect(dialog.getByRole("option", { name: /^Any product on Pet/ })).toBeVisible(); // a watchlist needs no search
  await search.fill("lamp");
  const lamp = dialog.getByRole("option", { name: new RegExp(`^${LAMP}`) });
  await expect(lamp).toContainText("Lamps");
  await lamp.click(); // 2
  await expect(page.getByRole("dialog", { name: `New alert rule on ${LAMP}` })).toBeVisible();
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toBeFocused();
  await expect(dialog.getByRole("combobox", { name: "Watch" })).toHaveValue("product");
  await dialog.getByRole("combobox", { name: "Event" }).selectOption("freight_change"); // 3
  await dialog.getByRole("button", { name: "Create rule" }).click(); // 4
  await expect(dialog).toBeHidden();
  await expect(newRule).toBeFocused();
  const name = `${LAMP}: freight ±5%`;
  expect(api.ruleWrites).toEqual([{ method: "POST", id: undefined, body: { name, type: "freight_change", target_type: "product", target_id: PRODUCT_ID, params: { pct: 5 }, enabled: true } }]);
  await expect(list(page).getByRole("rowheader").first()).toContainText(name);
});

test("keyboard only: N, a few letters and Enter pick the product; a 422 is in words; Escape gives focus back", async ({ page }) => {
  const { api, newRule, dialog, search } = await open(page);
  await page.keyboard.press("n");
  await expect(search).toBeFocused();
  await page.keyboard.type("sunset");
  await expect(dialog.getByRole("option", { name: new RegExp(`^${LAMP}`) })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");
  const watch = dialog.getByRole("combobox", { name: "Watch" });
  await expect(watch).toBeFocused();
  await expect(page.locator(":focus-visible")).toHaveAccessibleName("Watch"); // the ring shows
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const pct = dialog.getByRole("textbox", { name: "Change, %" });
  await expect(pct).toBeFocused();
  await page.keyboard.press("Control+A");
  await page.keyboard.type("0");
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("alert")).toHaveText("Enter a % above 0, up to 1,000."); // imp-585: never Pydantic's text
  await expect(pct).toHaveAttribute("aria-invalid", "true");
  await page.keyboard.press("Control+A");
  await page.keyboard.type("8");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(newRule).toBeFocused();
  expect(api.ruleWrites.at(-1)?.body).toMatchObject({ name: `${LAMP}: supplier price ±8%`, target_id: PRODUCT_ID, params: { pct: 8 } });

  await page.keyboard.press("n"); // from the button, N opens it again; Escape closes it
  await expect(search).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(newRule).toBeFocused();
  await page.getByRole("switch", { name: "Notify: Lamp: stock-out" }).focus();
  await page.keyboard.press("n"); // and from a row, it goes through the button
  await page.keyboard.press("Escape");
  await expect(newRule).toBeFocused();
});

test("a watchlist needs no product: its sentence offers the score verbs, and Change goes back (3 clicks)", async ({ page }) => {
  const { api, newRule, dialog, search } = await open(page);
  await newRule.click(); // 1
  await dialog.getByRole("option", { name: /^Any product on Pet/ }).click(); // 2
  await expect(page.getByRole("dialog", { name: "New alert rule on Pet" })).toBeVisible();
  const watch = dialog.getByRole("combobox", { name: "Watch" });
  await expect(watch).toBeFocused();
  await expect(watch).toHaveValue(`watchlist:${PET_LIST}`);
  await expect(watch.getByRole("option")).toHaveText(["any product on Pet"]);
  await expect(dialog.getByRole("combobox", { name: "Event" }).getByRole("option")).toHaveText(["velocity rises by", "Saturation crosses"]);
  await expect(dialog.getByRole("textbox", { name: "Name" })).toHaveAttribute("placeholder", "Pet: velocity +50%");

  await dialog.getByRole("button", { name: "Change product or watchlist" }).click();
  await expect(search).toBeFocused();
  await search.fill("pet");
  await expect(dialog.getByRole("option", { name: /^Any product on Pet/ })).toBeVisible(); // watchlists match by name
  await dialog.getByRole("option", { name: /^Any product on Pet/ }).click();
  await dialog.getByRole("button", { name: "Create rule" }).click(); // 3
  await expect(dialog).toBeHidden();
  expect(api.ruleWrites).toEqual([
    { method: "POST", id: undefined, body: { name: "Pet: velocity +50%", type: "velocity_spike", target_type: "watchlist", target_id: PET_LIST, params: { pct: 50, min_volume: 10 }, enabled: true } },
  ]);
  await expect(row(page, "Pet: velocity").getByRole("link", { name: "Pet" })).toHaveAttribute("href", `/watchlists?list=${PET_LIST}`);
});

test("the picker's states: hint, loading, stale, stores only, empty and too long", async ({ page }) => {
  const { newRule, dialog, search } = await open(page, { hold: ["lamp", "glow l"] });
  await newRule.click();
  await expect(dialog.getByRole("option", { name: "Type 2 or more characters to search products." })).toHaveAttribute("aria-disabled", "true");
  await search.fill("lamp"); // held
  await expect(dialog.getByRole("option", { name: "Searching products…" })).toBeVisible();
  await expect(dialog.getByTestId("picker-busy")).toBeVisible();
  await search.fill("glow");
  await expect(dialog.getByRole("option", { name: /^Glow-in-the-dark star projector/ })).toBeVisible();
  await expect(dialog.getByRole("status")).toHaveText("3 products for “glow”");
  await search.fill("glow l"); // held: the last results stay under the spinner
  await expect(dialog.getByTestId("picker-busy")).toBeVisible();
  await expect(dialog.getByRole("option", { name: /^Glow-in-the-dark star projector/ })).toBeVisible();
  await expect(dialog.getByRole("listbox")).toHaveAttribute("aria-busy", "true");
  await search.fill("glowbeam"); // only a store matches
  await expect(dialog.getByRole("option", { name: /^No products match “glowbeam”/ })).toBeVisible();
  await search.fill("zzzz");
  await expect(dialog.getByRole("option", { name: /^No products match “zzzz”/ })).toBeVisible();
  await expect(dialog.getByRole("option", { name: /^Any product on/ })).toHaveCount(0);
  await search.fill(LONG_URL);
  await expect(dialog.getByRole("option", { name: /^Too long to search: \d+ characters/ })).toBeVisible();
});

test("the picker's states: an error with Retry, and no products collected yet", async ({ page }) => {
  const { queries, newRule, dialog, search } = await open(page, { failures: 2 }); // the search retries once
  await newRule.click();
  await search.fill("lamp");
  await expect(dialog.getByRole("option", { name: /^Search unavailable/ })).toBeVisible();
  await dialog.getByRole("option", { name: "Retry search" }).click();
  await expect(dialog.getByRole("option", { name: new RegExp(`^${LAMP}`) })).toBeVisible();
  expect(queries).toEqual(["lamp", "lamp", "lamp"]);

  await page.unrouteAll({ behavior: "ignoreErrors" });
  const empty = await open(page, { catalogEmpty: true });
  await empty.newRule.click();
  await empty.search.fill("lamp");
  await expect(empty.dialog.getByRole("option", { name: /^No products collected yet/ })).toBeVisible();
  await empty.dialog.getByRole("option", { name: "Open Data Health" }).click();
  await expect(page).toHaveURL(/\/admin\/data-health$/);
});
