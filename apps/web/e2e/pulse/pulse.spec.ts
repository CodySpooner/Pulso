import { expect, test, type Locator, type Page } from "@playwright/test";

import { NOW } from "../data-health/fixtures";
import { LATEST, mockPulseApi, nothing, pulse } from "./fixtures";

// WF-6b (DEC-342): the Daily Pulse on fixture GET /v1/pulse responses under the E2E auth bypass, never a database restore.

const card = (page: Page, title: string) => page.locator("section").filter({ has: page.getByRole("heading", { level: 2, name: title, exact: true }) });

async function tabTo(page: Page, target: Locator, max = 80) {
  for (let i = 0; i < max && !(await target.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(target).toBeFocused();
  expect(await target.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none"); // the global :focus-visible ring
}

test("with the Shopify crawler off, the populated sections lead and the rest say no source yet", async ({ page }) => {
  await mockPulseApi(page);
  await page.goto("/");
  await expect(card(page, "Top emerging").getByRole("link", { name: "Sunset projection lamp with 16 colour modes" })).toBeVisible();
  expect(await page.locator("section[data-status=ok]").count()).toBeGreaterThanOrEqual(3);
  const launches = card(page, "New in tracked stores");
  await expect(launches).toContainText("No source yet");
  await expect(launches).toContainText("The Shopify store crawler is off.");
  const titles = await page.locator("section[data-status] h2").allTextContents();
  expect(titles.slice(-2)).toEqual(["New in tracked stores", "Margin changes"]);
  expect(titles[0]).toBe("Alerts"); // unread alerts lead
});

test("switching the day changes the URL, the request and each card's as of; Back steps back", async ({ page }) => {
  const api = await mockPulseApi(page);
  await page.goto("/");
  const lamp = card(page, "Top emerging").getByRole("link", { name: /^Sunset projection lamp/ });
  await expect(lamp).toHaveAttribute("title", "Trend Score · as of Oct 21, 06:10 UTC");
  await expect(page.getByRole("button", { name: "Next day" })).toBeDisabled(); // the latest day

  await page.getByRole("button", { name: "Previous day" }).click();
  await expect(page).toHaveURL(/\/\?date=2026-10-20$/);
  await expect(lamp).toHaveAttribute("title", "Trend Score · as of Oct 20, 06:10 UTC");
  await expect(page.getByText("Tue, Oct 20, 2026 (UTC day)")).toBeVisible();
  expect(api.dates.at(-1)).toBe("2026-10-20");

  await page.getByRole("button", { name: "Next day" }).click();
  await expect(page).toHaveURL(/\?date=2026-10-21$/);
  await page.getByRole("button", { name: "Latest" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "Latest" })).toBeDisabled();
  await page.goBack();
  await expect(page).toHaveURL(/\?date=2026-10-21$/);
  expect(api.dates).toEqual([null, "2026-10-20", "2026-10-21"]); // each day fetched once; the rest from the cache
});

test("a dated URL opens on that day", async ({ page }) => {
  const api = await mockPulseApi(page);
  await page.goto("/?date=2026-10-12");
  await expect(card(page, "Biggest movers").getByRole("link").first()).toHaveAttribute("title", "Trend Score · as of Oct 12, 06:10 UTC");
  expect(api.dates).toEqual(["2026-10-12"]);
});

test("the movers toggle switches Up and Down in one click, and deltas carry a sign and a glyph", async ({ page }) => {
  await mockPulseApi(page);
  await page.goto("/");
  const movers = card(page, "Biggest movers");
  await expect(movers.getByRole("listitem").first()).toContainText("▲+6.7");
  await movers.getByRole("button", { name: "Down" }).click();
  await expect(movers.getByRole("button", { name: "Down" })).toHaveAttribute("aria-pressed", "true");
  await expect(movers.getByRole("listitem").first()).toContainText("Mini waffle maker");
  await expect(movers.getByRole("listitem").first()).toContainText("▼−8.3");
});

test("the alerts card lists the day's alerts unread first and opens the inbox", async ({ page }) => {
  await mockPulseApi(page);
  await page.goto("/");
  const alerts = card(page, "Alerts");
  await expect(alerts).toContainText("2 unread");
  await expect(alerts.getByRole("listitem").first()).toContainText("Supplier ran out of stock");
  await alerts.getByRole("link", { name: "Open the alerts inbox" }).click();
  await expect(page).toHaveURL(/\/alerts$/);
  await expect(page.getByRole("heading", { level: 1, name: "Alerts" })).toBeVisible();
});

test("an item opens its product page", async ({ page }) => {
  await mockPulseApi(page);
  await page.goto("/");
  await card(page, "Search movers").getByRole("link", { name: "Portable neck fan, bladeless" }).click();
  await expect(page).toHaveURL(/\/products\/3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b02\?tab=trends$/);
});

test("keyboard only: the day switcher, the movers toggle and the rows are reachable with a visible ring", async ({ page }) => {
  await mockPulseApi(page);
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-app-ready", "true");
  await tabTo(page, page.getByRole("button", { name: "Previous day" }));
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\?date=2026-10-20$/);
  const down = card(page, "Biggest movers").getByRole("button", { name: "Down" });
  await tabTo(page, down);
  await page.keyboard.press("Space");
  await expect(down).toHaveAttribute("aria-pressed", "true");
  await tabTo(page, card(page, "Biggest movers").getByRole("link").first());
  await tabTo(page, card(page, "Watchlist").getByRole("combobox", { name: "Watchlist" }));
});

test("errors keep the header and offer Retry; a failed refresh keeps the day on screen", async ({ page }) => {
  const options: Parameters<typeof mockPulseApi>[1] = { status: 503 };
  await mockPulseApi(page, options);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 2, name: "Couldn’t load the Daily Pulse" })).toBeVisible();
  options.status = undefined;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(card(page, "Top emerging")).toBeVisible();

  options.status = 503; // the next refetch fails: TanStack refetches a stale query on focus
  await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000));
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("group", { name: "Couldn’t refresh the Daily Pulse" })).toBeVisible({ timeout: 15_000 });
  await expect(card(page, "Top emerging")).toBeVisible();
});

test("a latest day before yesterday says the scoring hasn't run; nothing collected shows the first-run card", async ({ page }) => {
  await mockPulseApi(page, { day: (d) => pulse(d ?? "2026-10-19") });
  await page.goto("/");
  await expect(page.getByText("Nothing scored since Mon, Oct 19, 2026.")).toBeVisible();
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockPulseApi(page, { day: (d) => nothing(d ?? LATEST) });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your first pulse arrives once collectors run" })).toBeVisible();
  await expect(page.locator("section[data-status=ok]")).toHaveCount(0);
});

test.describe("touch", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("375px: one column, no sideways scroll, and every control owns a 44px hit area", async ({ page }) => {
    await mockPulseApi(page);
    await page.goto("/");
    await expect(card(page, "Top emerging").getByRole("listitem").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    const small = await page.locator("main").evaluate((main) =>
      [...main.querySelectorAll<HTMLElement>("a[href], button, select")]
        .filter((el) => !el.matches(":disabled") && el.checkVisibility())
        .flatMap((el) => {
          el.scrollIntoView({ block: "center" });
          const r = el.getBoundingClientRect();
          const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2];
          return [-21, 0, 21].some((dx) => [-21, 0, 21].some((dy) => !el.contains(document.elementFromPoint(cx + dx, cy + dy)))) ? [el.textContent?.trim() || el.getAttribute("aria-label")] : [];
        }),
    );
    expect(small).toEqual([]);
  });
});
