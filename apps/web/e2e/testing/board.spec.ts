import { expect, test, type Page } from "@playwright/test";

import { mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { mockTestingApi } from "./fixtures";

// WF-5b Testing Board against fixture responses (the E2E auth bypass, never a database restore).
const column = (page: Page, label: string) => page.getByRole("region", { name: new RegExp(`^${label}\\b`) });
const card = (page: Page, label: string, title: string) => column(page, label).getByRole("article", { name: title });
const toast = (page: Page) => page.getByRole("status").filter({ hasText: /\S/ }).last();

test("a card moves through all five columns by keyboard only", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  await expect(card(page, "Idea", "Sunset projection lamp")).toBeVisible();
  await page.locator("#test-7").focus(); // the card's own button; from here on, keys only
  // The menu lists the other four columns in order and opens on the first; Radix moves focus a tick after each key.
  const moveTo = async (target: string) => {
    await page.keyboard.press("Tab"); // the card's "Move to…" menu
    await expect(page.getByRole("button", { name: "Move Sunset projection lamp to…" })).toBeFocused();
    await page.keyboard.press("Enter");
    const items = page.getByRole("menuitem");
    for (let i = 0; (await items.nth(i).textContent()) !== target; i++) {
      await expect(items.nth(i)).toBeFocused();
      await page.keyboard.press("ArrowDown");
    }
    await expect(page.getByRole("menuitem", { name: target })).toBeFocused();
    await page.keyboard.press("Enter");
  };
  await moveTo("Researching");
  await expect(card(page, "Researching", "Sunset projection lamp")).toBeVisible();
  await expect(page.locator("#test-7")).toBeFocused(); // focus follows the card
  await moveTo("Testing");
  await expect(card(page, "Testing", "Sunset projection lamp")).toBeVisible();
  await moveTo("Winner");
  await expect(card(page, "Winner", "Sunset projection lamp")).toBeVisible();
  await moveTo("Killed…"); // asks why first
  const dialog = page.getByRole("dialog", { name: "Why kill Sunset projection lamp?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "No sales over stop-loss" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(card(page, "Killed", "Sunset projection lamp")).toBeVisible();
  await expect(page.locator("#test-7")).toBeFocused();
  expect(api.patches).toEqual([
    { stage: "researching" },
    { stage: "testing" },
    { stage: "winner" },
    { stage: "killed", kill_reason: "no_sales_over_stop_loss" },
  ]);
  await expect(toast(page)).toContainText("Moved Sunset projection lamp to Killed.");
});

test("Killed needs a reason: cancelling moves nothing, a reason moves it and updates the counts", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  const killed = column(page, "Killed");
  await expect(killed.getByRole("heading")).toHaveText(/Killed\s*:?\s*2 tests/);
  await expect(killed.getByRole("list", { name: "Kill reasons" })).toHaveText(/Saturated market1.*CPA above break-even1/);

  await card(page, "Testing", "Posture corrector brace").getByRole("button", { name: /^Move/ }).click();
  await page.getByRole("menuitem", { name: "Killed…" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(card(page, "Testing", "Posture corrector brace")).toBeVisible();
  expect(api.patches).toEqual([]); // no reason, no move

  await card(page, "Testing", "Posture corrector brace").getByRole("button", { name: /^Move/ }).click();
  await page.getByRole("menuitem", { name: "Killed…" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Saturated market" }).click();
  await expect(card(page, "Killed", "Posture corrector brace")).toBeVisible();
  await expect(killed.getByRole("heading")).toHaveText(/3 tests/);
  await expect(killed.getByRole("list", { name: "Kill reasons" })).toHaveText(/Saturated market2.*CPA above break-even1/);
  expect(api.patches).toEqual([{ stage: "killed", kill_reason: "saturated" }]);

  await toast(page).getByRole("button", { name: "Undo" }).click(); // back to Testing, reason cleared
  await expect(card(page, "Testing", "Posture corrector brace")).toBeVisible();
  await expect(killed.getByRole("list", { name: "Kill reasons" })).toHaveText(/Saturated market1/);
  expect(api.patches.at(-1)).toEqual({ stage: "testing" });
});

test("a drag between columns persists after reload", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  const from = card(page, "Idea", "Sunset projection lamp");
  await expect(from).toBeVisible();
  const start = (await from.boundingBox())!;
  const target = (await column(page, "Researching").boundingBox())!;
  await page.mouse.move(start.x + start.width / 2, start.y + start.height - 8);
  await page.mouse.down();
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2, { steps: 12 });
  await page.mouse.up();
  await expect(card(page, "Researching", "Sunset projection lamp")).toBeVisible();
  expect(api.patches).toEqual([{ stage: "researching" }]);
  await page.reload();
  await expect(card(page, "Researching", "Sunset projection lamp")).toBeVisible();
  await expect(column(page, "Idea").getByText("No tests")).toBeVisible();
});

test("a failed move rolls back and says why", async ({ page }) => {
  await mockTestingApi(page, { failPatch: true });
  await page.goto("/testing");
  await card(page, "Idea", "Sunset projection lamp").getByRole("button", { name: /^Move/ }).click();
  await page.getByRole("menuitem", { name: "Testing" }).click();
  await expect(toast(page)).toContainText("Couldn't move Sunset projection lamp to Testing: The API is restarting. Try again. It's back in Idea.");
  await expect(card(page, "Idea", "Sunset projection lamp")).toBeVisible();
});

test("the drawer's CPA and ROAS match a hand calculation, and saving recomputes them", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  await card(page, "Testing", "Posture corrector brace").getByRole("button", { name: "Posture corrector brace", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "Posture corrector brace" });
  const figure = (label: string) => drawer.locator(`dt:text-is("${label}") + dd`);
  // $200.00 / 3 orders = $66.67; $259.99 / $200.00 = 1.29995 → 1.30×
  await expect(figure("CPA")).toHaveText("$66.67");
  await expect(figure("ROAS")).toHaveText("1.30×");
  // The worked example: $39.99 − $14.20 − $1.46 fees = $24.33; 39.99 / 24.33 = 1.64×
  await expect(figure("Price")).toHaveText("$39.99");
  await expect(figure("Landed cost")).toHaveText("$14.20");
  await expect(figure("Break-even CPA")).toHaveText("$24.33");
  await expect(figure("Break-even ROAS")).toHaveText("1.64×");

  await drawer.getByLabel("Ad spend").fill("48.65");
  await drawer.getByLabel("Orders").fill("2");
  await drawer.getByRole("button", { name: "Save metrics" }).click();
  await expect(drawer.getByRole("status")).toHaveText("Saved.");
  // $48.65 / 2 = $24.325 → $24.32 half-even; $259.99 / $48.65 = 5.344 → 5.34×
  await expect(figure("CPA")).toHaveText("$24.32");
  await expect(figure("ROAS")).toHaveText("5.34×");
  expect(api.patches).toEqual([{ ad_spend_minor: 4865, revenue_minor: 25999, orders: 2, started_on: "2026-10-19", ended_on: null, notes: null }]);
});

test("null metrics and an incomplete snapshot say no source yet, never 0", async ({ page }) => {
  await mockTestingApi(page);
  await page.goto("/testing");
  const idea = card(page, "Idea", "Sunset projection lamp");
  await expect(idea.getByText("No source yet: no orders recorded")).toBeAttached();
  await expect(idea.getByText("No source yet: no ad spend recorded")).toBeAttached();
  const projector = card(page, "Testing", "Galaxy star projector");
  await expect(projector.getByText("Metrics last updated")).toBeVisible(); // 72 h old: stale
  await projector.getByRole("button", { name: "Galaxy star projector", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Set price and supplier to compute break-even.");
});

test("a deep link opens the test, and Escape closes it", async ({ page }) => {
  await mockTestingApi(page);
  await page.goto("/testing?test=3");
  await expect(page.getByRole("dialog", { name: "Mini waffle maker" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("loading, empty and error states", async ({ page }) => {
  await mockTestingApi(page, { hold: true });
  await page.goto("/testing");
  await expect(page.getByRole("status", { name: "Loading your tests" })).toBeAttached();

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockTestingApi(page, { items: [] });
  await page.goto("/testing");
  await expect(page.getByRole("heading", { name: "No tests yet. Start one from a product page" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Find a product in Discover" })).toHaveAttribute("href", "/discover");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockTestingApi(page, { status: 503 });
  await page.goto("/testing");
  await expect(page.getByRole("heading", { name: "Couldn't load your tests" })).toBeVisible();
});

test("a failed refresh keeps the board and says how old it is", async ({ page }) => {
  const api = await mockTestingApi(page);
  await page.goto("/testing");
  await expect(card(page, "Idea", "Sunset projection lamp")).toBeVisible();
  api.failLists();
  await card(page, "Idea", "Sunset projection lamp").getByRole("button", { name: /^Move/ }).click();
  await page.getByRole("menuitem", { name: "Researching" }).click(); // the move saves; the refetch after it fails
  await expect(page.getByRole("group", { name: "Couldn't refresh your tests" })).toContainText("Showing data as of");
  await expect(card(page, "Researching", "Sunset projection lamp")).toBeVisible();
});

test("375px: moves through the menu, no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockTestingApi(page);
  await page.goto("/testing");
  await card(page, "Idea", "Sunset projection lamp").getByRole("button", { name: /^Move/ }).click();
  await page.getByRole("menuitem", { name: "Testing" }).click();
  await expect(card(page, "Testing", "Sunset projection lamp")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
});

test("Start a test on the Product Page adds an Idea test and links to it; a second says it's already there", async ({ page }) => {
  await mockProductApi(page);
  const api = await mockTestingApi(page, { items: [] });
  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("button", { name: "Start a test" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Added to Idea." })).toBeVisible();
  expect(api.posts).toEqual([{ product_id: PRODUCT_ID }]);
  await page.getByRole("link", { name: "Open the board" }).click();
  await expect(page).toHaveURL(/\/testing\?test=100$/);
  await expect(page.getByRole("dialog", { name: "Sunset projection lamp" })).toBeVisible();

  await page.goto(`/products/${PRODUCT_ID}`);
  await page.getByRole("button", { name: "Start a test" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Already on the board." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the board" })).toHaveAttribute("href", "/testing");
});

test("Testing cards show the API's stop-loss chip, day N and the spend bar (DEC-340)", async ({ page }) => {
  await mockTestingApi(page);
  await page.goto("/testing");
  // The worked example: no orders at $48.66, 2 × the $24.33 break-even CPA. Started Oct 19, on the fixture clock of Oct 22: day 4.
  const lights = card(page, "Testing", "LED strip lights");
  await expect(lights.getByText("Over stop-loss")).toBeVisible();
  await expect(lights.getByText("Day 4", { exact: true })).toBeVisible();
  await expect(lights.getByText(/^Stop-loss\s*\$48\.66$/)).toBeVisible(); // the spend bar's caption
  const winner = card(page, "Testing", "Heatless curling ribbon"); // 6 orders at $20.00 ≤ $24.33
  await expect(winner.getByText("Winner candidate")).toBeVisible();
  await expect(winner.getByText("Over stop-loss")).toHaveCount(0);
  // 3 orders: under N, so no call either way; an incomplete snapshot gives the reason, never a chip.
  await expect(card(page, "Testing", "Posture corrector brace").getByText(/Over stop-loss|Winner candidate/)).toHaveCount(0);
  const projector = card(page, "Testing", "Galaxy star projector");
  await expect(projector.getByText("Set price and supplier to compute break-even.")).toBeVisible();
  await expect(projector.getByText(/^Stop-loss/)).toHaveCount(0);
  await expect(card(page, "Winner", "Mini waffle maker").getByText(/Day \d|stop-loss/)).toHaveCount(0); // Testing only
});

test("the drawer lists what changed since start, by keyboard only, and the snapshot stays", async ({ page }) => {
  await mockTestingApi(page);
  await page.goto("/testing");
  await page.locator("#test-9").focus();
  await expect(page.locator("#test-9")).toBeFocused();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "LED strip lights" });
  await expect(drawer).toContainText("Suggested test budget $48.66: 2 × break-even CPA.");
  const changed = drawer.getByRole("list", { name: "Changed inputs" });
  await expect(changed.getByRole("listitem")).toHaveText([
    /Freight quote\s*Re-quoted\s*#41\s*→\s*changed to\s*#57/,
    /Freight\s*▲\+\$1\.20\s*\$4\.00\s*→\s*changed to\s*\$5\.20/,
    /Duty rate\s*▲\+5 pts\s*20%\s*→\s*changed to\s*25%/,
    /Break-even CPA\s*▼−\$1\.62\s*\$24\.33\s*→\s*changed to\s*\$22\.71/,
  ]);
  await expect(drawer.locator('dt:text-is("Break-even CPA") + dd')).toHaveText("$24.33"); // the start snapshot, as it was
  await expect(drawer).toContainText("data as of");
  // Tab walks the drawer with a visible ring; Escape closes it and focus is back on the card.
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle !== "none" || getComputedStyle(document.activeElement!).boxShadow !== "none")).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.locator("#test-9")).toBeFocused();
});

test("changed since start: nothing changed, a calc that can't run, and a failed request", async ({ page }) => {
  await mockTestingApi(page, {
    sinceStart: { 1: "error", 2: { changes: [], reason: "Supplier listing not found on this product.", as_of: null } },
  });
  await page.goto("/testing?test=3");
  await expect(page.getByRole("dialog", { name: "Mini waffle maker" })).toContainText("No changes since start.");
  await page.goto("/testing?test=2");
  await expect(page.getByRole("dialog")).toContainText("Can't compare with today's numbers: Supplier listing not found on this product. Check the Profit tab");
  await page.goto("/testing?test=1");
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Couldn't compare with today's numbers" })).toBeVisible();
  await page.goto("/testing?test=7"); // no snapshot yet: no comparison
  await expect(page.getByRole("dialog", { name: "Sunset projection lamp" })).not.toContainText("Changed since start");
});
