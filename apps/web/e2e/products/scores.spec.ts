import { expect, test, type Page } from "@playwright/test";

import { feedItems, mockFeedApi, mockProductApi, PRODUCT_ID, product } from "./fixtures";
import { scoresNone, scoresStale, scoresUnscored } from "./scores-fixtures";

// imp-460 (SC-5 / WF-1): the Overview's score cards and Discover's Trend cell, against fixture responses (the E2E auth
// bypass, never a database restore).
const URL = `/products/${PRODUCT_ID}`;
const cards = (page: Page) => page.locator("article[data-score]");
const card = (page: Page, kind: string) => page.locator(`#score-${kind}`);
const tooltip = (page: Page, text: string) => page.getByRole("tooltip").filter({ hasText: text });
const grid = (page: Page) => page.locator('section[aria-labelledby="key-stats"] dl');

test("ff_scores on: four score cards, each with its as of, reasons and a methodology link by keyboard", async ({ page }) => {
  const calls = await mockProductApi(page);
  await page.goto(URL);
  await expect(cards(page).locator("h3")).toHaveText(["Trend Score", "Opportunity", "Saturation", "Lifecycle"]);
  expect(calls.some((u) => u.includes(`/${PRODUCT_ID}/scores?range=7d&limit=1`))).toBe(true);

  const trend = card(page, "trend");
  await expect(trend).toContainText("Beta");
  await expect(trend).toContainText("68.6/ 100");
  await expect(trend).toContainText("Coverage85%High");
  // The top 3 reasons in points (50/3 × contribution), then the penalty as its own step, then what is missing.
  await expect(trend.getByRole("listitem")).toHaveText([
    "▲Velocity growth (Shopify inventory)+15.3 points",
    "▲Search-interest slope+5.5 points",
    "▲Acceleration (Shopify inventory)+4.7 points",
    "▼Saturation penalty−7.0 points",
  ]);
  await expect(trend).toContainText("No source yet: Ad-count growth");
  await expect(trend).toContainText("As of Oct 21");

  const opportunity = card(page, "opportunity");
  await expect(opportunity).toContainText("65.7/ 100");
  await expect(opportunity.getByText("Duty not set")).toHaveClass(/bg-warning-muted/);
  await expect(opportunity).toContainText("Confidence70%Medium");
  await expect(opportunity).toContainText("No source yet: Safety (100 − Risk)");
  await expect(card(page, "saturation")).toContainText("73.3/ 100 · High");
  await expect(card(page, "lifecycle")).toContainText("RisingRule: growingPending: peaking, shown once a second night agrees.");
  await expect(card(page, "lifecycle")).not.toContainText("Beta");

  // A reason's source and a row's cutoff open on keyboard focus.
  await trend.getByRole("button", { name: "Search-interest slope" }).focus();
  await expect(tooltip(page, "Source")).toContainText("Source: Google Trends");
  await trend.getByRole("button", { name: "As of Oct 21" }).focus();
  await expect(tooltip(page, "Scored for")).toContainText("Scored for Oct 21 (UTC) from data captured before Oct 22, 00:00 UTC. Model 000-8236875f835c.");

  // MT-1: Tab from the as of reaches the definition, with a visible focus ring; Enter opens its anchor.
  await page.keyboard.press("Tab");
  const how = trend.getByRole("link", { name: "How Trend Score works" });
  await expect(how).toBeFocused();
  await expect(how).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/methodology#trend-score");
});

test("ff_scores off: no scores request and the page is unchanged", async ({ page }) => {
  const calls = await mockProductApi(page);
  await page.goto(`${URL}?ff_scores=off`);
  await expect(grid(page).locator("dt")).toHaveText(["Price range", "Best supplier cost", "Landed margin", "First seen", "Velocity 7d"]);
  await expect(page.getByRole("tabpanel")).not.toContainText(/Trend Score|Saturation|Lifecycle|Opportunity/);
  await expect(cards(page)).toHaveCount(0);
  expect(calls.filter((u) => u.includes("/scores"))).toEqual([]);
});

test("NULL rows read insufficient signal with their reason; no rows read no source yet; the floor caps Opportunity", async ({ page }) => {
  await mockProductApi(page, { scores: scoresUnscored });
  await page.goto(URL);
  await expect(card(page, "trend")).toContainText("Insufficient signal · no velocity growth");
  await expect(card(page, "saturation")).toContainText("Insufficient signal · no seller count");
  await expect(card(page, "lifecycle")).toContainText("Insufficient signal · insufficient history");
  await expect(card(page, "trend")).toContainText("As of Oct 21"); // a NULL row still has its day
  const opportunity = card(page, "opportunity");
  await expect(opportunity).toContainText("25.0/ 100");
  await expect(opportunity.getByText("Margin below your floor").first()).toHaveClass(/bg-negative-muted/);
  await expect(opportunity.getByRole("listitem")).toHaveText(["▲Margin vs your floor+40.0 points", "▼Margin below your floor−15.0 points"]);
  await expect(opportunity).toContainText("Insufficient signal: Momentum (Trend Score), Room (100 − Saturation)");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { scores: scoresNone });
  await page.goto(URL);
  for (const kind of ["trend", "opportunity", "saturation", "lifecycle"]) {
    await expect(card(page, kind)).toContainText("No source yet");
    await expect(card(page, kind)).not.toContainText(/\d+\.\d|As of/); // never 0, and nothing to date
  }
});

test("loading, a failed load with Retry while the key stats render, and a stale row", async ({ page }) => {
  await mockProductApi(page, { holdScores: true });
  await page.goto(URL);
  await expect(page.getByRole("status").filter({ hasText: "Loading the scores…" })).toBeAttached();
  await expect(grid(page)).toContainText("$24.00–$39.99"); // the key stats never wait on the scores

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { scoresStatus: 503 });
  await page.goto(URL);
  await expect(page.getByRole("heading", { name: "Couldn't load the scores" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(grid(page)).toContainText("$24.00–$39.99");

  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mockProductApi(page, { scores: scoresStale });
  await page.goto(URL);
  await expect(card(page, "trend").getByRole("button", { name: "As of Oct 16 · stale" })).toHaveClass(/text-warning/);
});

test("Discover: a row's Trend cell opens the product's Trend card in one click, landed on and focused", async ({ page }) => {
  const items = feedItems(20);
  const first = items[0];
  await mockFeedApi(page, { items });
  await mockProductApi(page, { body: { ...product, id: first.id, title: first.title } });
  await page.goto("/discover?view=table");
  const table = page.getByRole("region", { name: "Products" });
  await expect(table.getByRole("link", { name: "Trend", exact: true })).toHaveAttribute("href", "/methodology#trend-score");
  const cell = table.locator("tbody tr").first().getByRole("link", { name: /^Trend Score: / });
  await expect(cell).toHaveText(`${(first.trend as { value: number }).value.toFixed(1)}β`);
  await expect(cell).toHaveAttribute("title", "Trend Score · as of Oct 21, from data before Oct 22, 00:00 UTC");
  // The same NULL and no-row wording as the card; the reason is on hover.
  await expect(table.getByRole("link", { name: /^Trend Score: Insufficient signal\. Insufficient signal · no velocity growth/ }).first()).toBeVisible();
  await expect(table.getByRole("link", { name: /^Trend Score: No source yet\./ }).first()).toBeVisible();

  await cell.click();
  await expect(page).toHaveURL(`/products/${first.id}#score-trend`);
  await expect(card(page, "trend")).toBeFocused();
  await expect(card(page, "trend")).toBeInViewport();
});
