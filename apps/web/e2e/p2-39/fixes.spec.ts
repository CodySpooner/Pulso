import { expect, test } from "@playwright/test";

import { mockPopularApi } from "../google-popular/fixtures";
import { detail, mockMatchingApi, title } from "../matching/fixtures";
import { mockFeedApi, mockProductApi, overview, PRODUCT_ID } from "../products/fixtures";
import { mockSuppliersApi } from "../products/suppliers-fixtures";
import { contrastMisses } from "./screens";

// p2-39 (Phase 2 end): one check per fix the phase-end review made (docs/reports/p2-39.md), from fixtures only.
const PRODUCT = `/products/${PRODUCT_ID}`;
const utc = /[A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2} UTC/;

// Store Spy, the one Phase 3 page left unbuilt, has no source instead (DEC-261, DEC-302 a): e2e/p3-10/states.ts.
// p3-12 moved the build to Phase 4, so a later page names it and every Phase 4 page is under way, never a 404.
test("the coming-soon page says Pulso is in Phase 4 (DEC-284)", async ({ page }) => {
  await page.goto("/ask");
  await expect(page.getByRole("heading", { name: "Ask Pulso arrives in Phase 5" })).toBeVisible();
  await expect(page.getByRole("main")).toContainText("Phase 5, AI layer, builds this page. Pulso is in Phase 4, Scores & workflow.");
  await expect(page.getByRole("main")).toContainText("Now: Phase 4 · Scores & workflowThis page: Phase 5 · AI layer");
});

for (const [path, label] of [
  ["/alerts", "Alerts"],
  ["/screener", "Screener"],
  ["/watchlists", "Watchlists"],
  ["/boards", "Boards"],
  ["/testing", "Testing"],
  ["/methodology", "Methodology"],
])
  test(`${label}, a Phase 4 page, says Phase 4 is under way`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: `${label} arrives in Phase 4` })).toBeVisible();
    await expect(page.getByRole("main")).toContainText("Phase 4, Scores & workflow, is under way and builds this page.");
    await expect(page.getByRole("main")).toContainText("Now: Phase 4 · Scores & workflow");
  });

for (const theme of ["dark", "light"] as const)
  test(`a note that is still saving keeps AA contrast (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await mockProductApi(page, { holdSaves: true });
    await page.goto(PRODUCT);
    await page.getByRole("textbox", { name: "Add a note" }).fill("Pending thought");
    await page.getByRole("button", { name: "Add note" }).click();
    await expect(page.getByText("Saving…")).toBeVisible();
    await page.waitForTimeout(300);
    expect(await page.evaluate(contrastMisses, "[aria-label='Notes, newest first']")).toEqual([]);
  });

test("the rail's tags and notes announce their first load", async ({ page }) => {
  await mockProductApi(page, { holdRail: true });
  await page.goto(PRODUCT);
  await expect(page.getByRole("status").filter({ hasText: "Loading tags…" })).toBeAttached();
  await expect(page.getByRole("status").filter({ hasText: "Loading notes…" })).toBeAttached();
});

test("the velocity gap chip opens its reason from the keyboard", async ({ page }) => {
  await mockProductApi(page, { overview: { ...overview, velocity: { ...overview.velocity, gap: true } as typeof overview.velocity } });
  await page.goto(PRODUCT);
  await page.getByRole("button", { name: "gap" }).focus();
  await expect(page.getByRole("tooltip")).toHaveText("The 7-day window overlaps a collection gap");
});

test("a supplier's shipping days name the freight quote's source and as-of", async ({ page }) => {
  await mockSuppliersApi(page);
  await page.goto(`${PRODUCT}?tab=suppliers`);
  const days = page.getByRole("region", { name: "Suppliers" }).locator("span[title*='the carrier']").first();
  await expect(days).toHaveAttribute("title", new RegExp(`before supplier processing · CJ Dropshipping, as of ${utc.source}$`));
});

test("Matching: the queue score and the score panel say which matcher scored the pair, and when", async ({ page }) => {
  await mockMatchingApi(page);
  await page.goto("/admin/matching");
  await expect(page.getByRole("article", { name: `Listing A: ${title(0, "a")}` })).toBeVisible();
  await expect(page.locator("[title^='Matcher ']").first()).toHaveAttribute("title", new RegExp(`^Matcher \\S+ · scored ${utc.source}$`));
  await expect(page.locator("section[aria-labelledby=scores-title]")).toContainText(new RegExp(`· scored ${utc.source}`));
});

test("Matching: the split dialog's product picker is a set of toggle buttons", async ({ page }) => {
  await mockMatchingApi(page);
  const two = detail(0);
  two.clusters = two.clusters.map((c) => ({ ...c, listings: 2, members: [...c.members, ...c.members.map((m) => ({ ...m, listing_id: m.listing_id + 50 }))] }));
  await page.route(/\/api\/v1\/admin\/matching\/candidates\/1000$/, (route) => route.fulfill({ json: two }));
  await page.goto("/admin/matching");
  await expect(page.getByRole("article", { name: `Listing A: ${title(0, "a")}` })).toBeVisible();
  await page.keyboard.press("x");
  const picker = page.getByRole("dialog", { name: "Split a product" }).getByRole("group", { name: "Product" });
  await expect(picker.getByRole("button", { pressed: true })).toHaveCount(1);
  await picker.getByRole("button", { pressed: false }).click();
  await expect(picker.getByRole("button").last()).toHaveAttribute("aria-pressed", "true");
});

test.describe("375px touch", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });
  test("Matching's filter selects reach the touch input height", async ({ page }) => {
    await mockMatchingApi(page);
    await page.goto("/admin/matching");
    for (const select of await page.getByRole("group", { name: "Sort and filter" }).getByRole("combobox").all())
      expect((await select.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  });
});

test("a Discover card's first-seen date has its own UTC hover", async ({ page }) => {
  await mockFeedApi(page);
  await page.goto("/discover?view=grid");
  const card = page.getByRole("list", { name: "Products" }).getByRole("article").first();
  await expect(card.locator("time[title^='First seen']")).toHaveAttribute("title", new RegExp(`^First seen ${utc.source}$`));
});

test("Google popular: one term for major brands, and each price names its report", async ({ page }) => {
  await mockPopularApi(page);
  await page.goto("/google-popular");
  await expect(page.getByRole("main")).toContainText("Major brands are hidden");
  const price = page.getByRole("main").getByRole("row").nth(1).getByRole("cell").last();
  await expect(price).toHaveAttribute("title", /^Google Merchant Center Popular products · week of Oct 19, 2026 · imported /);
});
