import { expect, test, type Page } from "@playwright/test";

import { mockMatchingApi, title } from "./fixtures";

// UX-1 Matching Queue against fixture responses (the E2E auth bypass, never a database restore).
const pair = (page: Page, i: number) => page.getByRole("article", { name: `Listing A: ${title(i, "a")}` });
const toast = (page: Page) => page.getByRole("status").filter({ hasText: /\S/ }).last();

test("keyboard only: 200 pairs labelled with one key each, well under 30 minutes", async ({ page }) => {
  const api = await mockMatchingApi(page, { count: 200 });
  await page.goto("/admin/matching");
  await expect(pair(page, 0)).toBeVisible();
  const started = Date.now();
  let presses = 0;
  for (let i = 0; i < 200; i++) {
    await expect(pair(page, i)).toBeVisible(); // the owner looks, then decides
    await page.keyboard.press(i % 4 === 3 ? "r" : "a");
    presses++;
  }
  await expect(page.getByRole("heading", { name: "Queue clear" })).toBeVisible();
  const seconds = (Date.now() - started) / 1000;
  await expect.poll(() => api.posts.length).toBe(200);
  expect(api.posts.map((body) => body.candidate_id)).toEqual(api.all.map((row) => row.id));
  expect(api.posts.filter((body) => body.action === "reject")).toHaveLength(50);
  expect(presses / api.posts.length).toBe(1);
  test.info().annotations.push({ type: "keypresses per decision", description: "1" }, { type: "200 decisions, machine time", description: `${seconds.toFixed(1)} s` });
  expect(seconds).toBeLessThan(30 * 60);
  await expect(page.getByText("You decided 200 pairs this session.")).toBeVisible();
});

test("J and K move, S skips, 1–4 pick the image, U and Ctrl+Z undo", async ({ page }) => {
  const api = await mockMatchingApi(page);
  await page.goto("/admin/matching");
  await expect(pair(page, 0)).toBeVisible();
  await page.keyboard.press("j");
  await expect(pair(page, 1)).toBeVisible();
  await expect(page.locator('[aria-current="true"]')).toContainText(title(1, "a"));
  await page.keyboard.press("k");
  await expect(pair(page, 0)).toBeVisible();
  await page.keyboard.press("k"); // stops at the top
  await expect(pair(page, 0)).toBeVisible();
  await page.keyboard.press("3");
  await expect(page.getByRole("article", { name: /^Listing B/ }).getByText("Image 3, shown")).toBeAttached();
  await page.keyboard.press("s");
  await expect(pair(page, 1)).toBeVisible();
  expect(api.posts).toEqual([]); // a skip stays pending and writes nothing

  await page.keyboard.press("a");
  await expect(pair(page, 2)).toBeVisible();
  await expect(toast(page)).toContainText("Accepted pair #1001.");
  await page.keyboard.press("u");
  await expect(pair(page, 1)).toBeVisible(); // back, and selected
  await expect(toast(page)).toContainText("Undone: Accepted pair #1001");
  expect(api.undos).toEqual([9000]);

  await page.keyboard.press("r");
  await expect(pair(page, 2)).toBeVisible();
  await page.keyboard.press("Control+z");
  await expect(pair(page, 1)).toBeVisible();
  expect(api.posts).toEqual([
    { action: "accept", candidate_id: 1001 },
    { action: "reject", candidate_id: 1001 },
  ]);
  expect(api.undos).toEqual([9000, 9002]); // the first undo took 9001
  await page.keyboard.press("u");
  await expect(toast(page)).toContainText("Nothing to undo yet.");
});

test("merge and split dialogs show what moves before anything is confirmed", async ({ page }) => {
  const api = await mockMatchingApi(page);
  await page.goto("/admin/matching");
  await expect(pair(page, 0)).toBeVisible(); // two products, one of three listings

  await page.keyboard.press("m");
  const merge = page.getByRole("dialog", { name: "Merge two products" });
  await expect(merge).toContainText("Moves to Sunset projection lamp1 listing, one logged decision each");
  await merge.getByRole("button", { name: "Swap direction" }).click();
  await expect(merge).toContainText("Moves to Sunset projection lamp (CJ)3 listings");
  await expect(merge).toContainText("Your 2 notes and 1 tag, plus forecasts, scores and daily features");
  await page.keyboard.press("a"); // keys inside a dialog never decide the pair underneath
  expect(api.posts).toEqual([]);
  await merge.getByRole("button", { name: "Merge 3 listings" }).click();
  await expect(merge).toBeHidden();
  expect(api.posts.at(-1)).toMatchObject({ action: "merge", product_id: "0b1c2d3e-0000-4000-8000-000000000001", into: "0b1c2d3e-0000-4000-8000-000000000002" });

  await expect(pair(page, 0)).toBeVisible();
  await page.keyboard.press("x");
  const split = page.getByRole("dialog", { name: "Split a product" });
  await expect(split.getByRole("checkbox")).toHaveCount(3);
  await expect(split.getByRole("button", { name: "Split off" })).toHaveAttribute("aria-disabled", "true");
  await split.getByRole("checkbox").first().focus();
  await page.keyboard.press("Space");
  await expect(split.getByRole("status")).toHaveText("1 move · 2 stay on Sunset projection lamp");
  await split.getByRole("button", { name: "Split 1 listing off" }).click();
  await expect(split).toBeHidden();
  expect(api.posts.at(-1)).toEqual({ action: "split", listing_ids: [50_000] });

  await page.keyboard.press("j"); // pair 1: neither listing on a product
  await expect(pair(page, 1)).toBeVisible();
  await page.keyboard.press("m");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(toast(page)).toContainText("Merge needs both listings on products.");
  await page.keyboard.press("Escape");
});

test("a superseded pair is skipped, a failed pair can be skipped with J, missing images read n/a", async ({ page }) => {
  await mockMatchingApi(page, { superseded: [1000], failDetail: [1001], brokenImages: [1002], noImages: [1003] });
  await page.goto("/admin/matching");
  await expect(page.getByRole("heading", { name: "Couldn't load pair #1001" })).toBeVisible();
  await expect(page.getByText("Pair #1000 was superseded by another decision, so it was skipped.")).toBeVisible();
  await expect(page.getByText("Skip to the next one with J.")).toBeVisible();
  await page.keyboard.press("a"); // nothing on screen to decide
  await expect(toast(page)).toContainText("Pair #1001 didn't load. J skips to the next one.");
  await page.keyboard.press("j");
  await expect(pair(page, 2)).toBeVisible();
  await expect(pair(page, 2).getByText("Image unavailable")).toBeVisible(); // the stored components still score
  await page.keyboard.press("j");
  await expect(pair(page, 3)).toBeVisible();
  await expect(pair(page, 3).getByText("No image stored")).toBeVisible();
  const scores = page.getByRole("region", { name: "Score" });
  await expect(scores.getByText(/^n\/a: No image stored for one side$/)).toHaveCount(2); // image and pHash; the decision still works
  await page.keyboard.press("a");
  await expect(pair(page, 4)).toBeVisible();
});

test("an empty queue reads Queue clear with the matcher's summary", async ({ page }) => {
  await mockMatchingApi(page, { count: 0 });
  await page.goto("/admin/matching");
  await expect(page.getByRole("heading", { name: "Queue clear" })).toBeVisible();
  await expect(page.getByText(/The matcher has auto-linked 412 listings; the last on Oct 22, 03:12 UTC\./)).toBeVisible();
});

test("one stored source reads no source yet, without promising Shopify", async ({ page }) => {
  await mockMatchingApi(page, { count: 0, summary: { stored_sources: ["cj"], matcher_enabled: false } });
  await page.goto("/admin/matching");
  const empty = page.getByRole("region", { name: "Matching queue" });
  await expect(empty.getByRole("heading", { name: "Matching needs at least two stored sources" })).toBeVisible();
  await expect(empty).toContainText("Only CJ listings are stored today.");
  await expect(empty).not.toContainText("Shopify");
  await expect(empty.getByRole("link", { name: "Open Data Health" })).toHaveAttribute("href", "/admin/data-health");
});

test("loading shows the final layout's skeletons", async ({ page }) => {
  await mockMatchingApi(page, { hold: true });
  await page.goto("/admin/matching");
  await expect(page.locator(".bg-skeleton").first()).toBeVisible();
});

test("a failed load offers Retry", async ({ page }) => {
  await mockMatchingApi(page, { status: 503 });
  await page.goto("/admin/matching");
  await expect(page.getByRole("heading", { name: "Couldn't load the queue" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("keyboard focus is visible on the queue rows and decision buttons", async ({ page }) => {
  await mockMatchingApi(page);
  await page.goto("/admin/matching");
  await expect(pair(page, 0)).toBeVisible();
  await page.getByRole("combobox", { name: /^Matcher/ }).focus();
  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toHaveAttribute("aria-current", "true");
  expect(await focused.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter"); // a row is a button: Enter selects it
  await expect(pair(page, 0)).toBeVisible();
});

test.describe("phone", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("read-only queue with Accept and Reject buttons, no merge or split, no sideways scroll", async ({ page }) => {
    const api = await mockMatchingApi(page);
    await page.goto("/admin/matching");
    await expect(pair(page, 0)).toBeVisible();
    const bar = page.getByRole("toolbar", { name: "Decision" });
    await expect(bar.getByRole("button", { name: /^Merge/ })).toBeHidden();
    await expect(bar.getByRole("button", { name: /^Split/ })).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    await bar.getByRole("button", { name: /^Reject/ }).tap();
    await expect(pair(page, 1)).toBeVisible();
    expect(api.posts).toEqual([{ action: "reject", candidate_id: 1000 }]);
  });
});
