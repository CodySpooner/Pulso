import { expect, test, type Locator, type Page } from "@playwright/test";

import { manyGaps, manyTargets, mockAdminApi, NOW, problem, sources } from "./fixtures";

// imp-075 (DEC-166): Load more reaches every open gap and run target past the first bounded page, once each,
// only when asked, with focus kept on the control. 260 items: the first page (50), one Load more page (200),
// then the last 10. imp-112: a failed page's Retry says what it retries, and "loaded" is said only by the footer note.

const PAGE = "/admin/data-health";

/** The cursor and limit of every request to an admin path, in order. */
function requests(page: Page, path: RegExp): { cursor: string | null; limit: string | null }[] {
  const seen: { cursor: string | null; limit: string | null }[] = [];
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (path.test(url.pathname)) seen.push({ cursor: url.searchParams.get("cursor"), limit: url.searchParams.get("limit") });
  });
  return seen;
}

/** Holds requests for one cursor until released, so the pending state can be checked. */
async function hold(page: Page, path: string, cursor: string): Promise<() => void> {
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(`**/api${path}?*`, async (route) => {
    if (new URL(route.request().url()).searchParams.get("cursor") === cursor) await held;
    await route.fallback();
  });
  return release;
}

/** Fails the first `times` requests for one cursor with a 503 problem. */
async function fail(page: Page, path: string, cursor: string, times: number) {
  await page.route(`**/api${path}?*`, async (route) => {
    if (new URL(route.request().url()).searchParams.get("cursor") === cursor && times-- > 0) return route.fulfill({ status: 503, json: problem(503, "req-load-more") });
    await route.fallback();
  });
}

test("open gaps: Load more traverses 260 gaps once each, keeping keyboard focus", async ({ page }) => {
  await mockAdminApi(page, { gaps: manyGaps(260) });
  const seen = requests(page, /^\/api\/v1\/admin\/host$/);
  const release = await hold(page, "/v1/admin/host", "gap-49");
  await page.goto(PAGE);
  const panel = page.getByRole("region", { name: "Coverage" });
  const rows = panel.getByRole("region", { name: "Open gaps" }).getByRole("row");
  await expect(rows).toHaveCount(1 + 8);
  await expect(panel).toContainText("Showing 8 of 50 ranges · 50 missed slots loaded, older gaps not loaded yet");
  await expect(panel.getByRole("heading", { name: /^Open gaps/ })).toHaveText(/^Open gaps · 50 ranges, newest first/);
  await expect(panel.getByText(/loaded/)).toHaveCount(1); // the footer note only

  const more = panel.getByRole("button", { name: /^(Load older gaps|Loading…|Retry loading older gaps)$/ }); // its label follows its state
  await expect(more).toHaveText("Load older gaps");
  await more.focus();
  await page.keyboard.press("Enter");
  await expect(more).toHaveAttribute("aria-disabled", "true");
  await expect(more).toHaveText("Loading…");
  await page.keyboard.press("Enter"); // pending: a second press sends nothing
  release();
  await expect(rows).toHaveCount(1 + 250);
  await expect(panel).toContainText("Showing 250 ranges · 250 missed slots loaded, older gaps not loaded yet");
  await expect(more).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(rows).toHaveCount(1 + 260);
  await expect(more).toHaveCount(0);
  const note = panel.getByText("Showing 260 ranges · all 260 missed slots in the last 90 days");
  await expect(note).toBeFocused(); // the button is gone; focus lands on the count, not the page
  const missed = await rows.locator("td:nth-child(2)").allTextContents();
  expect(new Set(missed).size).toBe(260);
  // One first page (the host card's), then one page per press: never the whole history at once.
  expect(seen).toEqual([
    { cursor: null, limit: null },
    { cursor: "gap-49", limit: "200" },
    { cursor: "gap-249", limit: "200" },
  ]);
});

test("open gaps: a failed page retries in place; Refresh keeps pages unless the first page moved", async ({ page }) => {
  const gaps = manyGaps(260);
  await mockAdminApi(page, { gaps });
  await fail(page, "/v1/admin/host", "gap-49", 2); // the query retries once before it shows the error
  const seen = requests(page, /^\/api\/v1\/admin\/host$/);
  await page.goto(PAGE);
  const panel = page.getByRole("region", { name: "Coverage" });
  const rows = panel.getByRole("region", { name: "Open gaps" }).getByRole("row");
  await panel.getByRole("button", { name: "Load older gaps" }).click();
  await expect(panel).toContainText("Couldn't load older gaps. The API is restarting. Try again.");
  await expect(panel).toContainText("Error ID req-load-more");
  await expect(rows).toHaveCount(1 + 50); // the press still shows every loaded range; nothing older is claimed
  await expect(panel).toContainText("Showing 50 ranges · 50 missed slots loaded, older gaps not loaded yet");
  await expect(panel.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  await panel.getByRole("button", { name: "Retry loading older gaps" }).click();
  await expect(rows).toHaveCount(1 + 250);
  await expect(panel).not.toContainText("Couldn't load older gaps");

  // The same first page: the loaded page refetches and stays.
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect.poll(() => seen.filter((r) => r.cursor === "gap-49").length).toBe(4);
  await expect(rows).toHaveCount(1 + 250);

  // A newer gap moves the first page's cursor: back to the first page, and nothing older loads by itself.
  gaps.unshift({ ...gaps[0], slot_key: "gap-new", slot_start: "2026-10-22T13:00:00Z", slot_end: "2026-10-22T14:00:00Z" });
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(rows).toHaveCount(1 + 8);
  await expect(panel).toContainText("Showing 8 of 50 ranges");
  await expect(panel.getByRole("button", { name: "Load older gaps" })).toBeVisible();
  expect(seen.some((r) => r.cursor !== null && r.cursor !== "gap-49")).toBe(false);
});

test("open gaps: the eight-range preview expands without a request when the first page is complete", async ({ page }) => {
  await mockAdminApi(page, { gaps: manyGaps(12) });
  const seen = requests(page, /^\/api\/v1\/admin\/host$/);
  await page.goto(PAGE);
  const panel = page.getByRole("region", { name: "Coverage" });
  const rows = panel.getByRole("region", { name: "Open gaps" }).getByRole("row");
  await expect(panel).toContainText("Showing 8 of 12 ranges · all 12 missed slots in the last 90 days");
  await panel.getByRole("button", { name: "Show 4 older ranges" }).click();
  await expect(rows).toHaveCount(1 + 12);
  await expect(panel).toContainText("Showing 12 ranges · all 12 missed slots in the last 90 days");
  expect(seen).toEqual([{ cursor: null, limit: null }]);
});

test("run targets: Load more traverses 260 targets once each; reopening starts over", async ({ page }) => {
  await mockAdminApi(page, { targets: manyTargets(260) });
  const seen = requests(page, /^\/api\/v1\/admin\/runs\/412$/);
  const release = await hold(page, "/v1/admin/runs/412", "store-050.example");
  await fail(page, "/v1/admin/runs/412", "store-250.example", 2);
  await page.goto(PAGE);
  await page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Shopify stores: open runs" }).click();
  const drawer = page.getByRole("dialog", { name: "Shopify stores" });
  const rows = drawer.getByRole("region", { name: "Run 412 targets" }).getByRole("row");
  await expect(rows).toHaveCount(1 + 50);
  await expect(drawer).toContainText("Showing 50 of 260 targets");

  const more = drawer.getByRole("button", { name: /^(Load more targets|Loading…|Retry loading targets)$/ });
  await expect(more).toHaveText("Load more targets");
  await more.focus();
  await page.keyboard.press("Enter");
  await expect(more).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Enter");
  release();
  await expect(rows).toHaveCount(1 + 250);
  await expect(drawer).toContainText("Showing 250 of 260 targets");
  await expect(more).toBeFocused();

  // The next page fails: the rows stay, and the same button retries it.
  await page.keyboard.press("Enter");
  await expect(drawer).toContainText("Couldn't load more targets.");
  await expect(more).toHaveText("Retry loading targets");
  await expect(more).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(rows).toHaveCount(1 + 260);
  await expect(more).toHaveCount(0);
  await expect(drawer.getByText("Showing all 260 targets")).toBeFocused();
  const ids = await rows.locator("td:first-child").allTextContents();
  expect(new Set(ids).size).toBe(260);
  const loaded = seen.filter((r) => r.cursor !== null);
  expect(seen.filter((r) => r.cursor === null)).toEqual([{ cursor: null, limit: null }]); // the first page as before
  expect(loaded.filter((r) => r.cursor === "store-050.example")).toEqual([{ cursor: "store-050.example", limit: "200" }]);
  expect(loaded.every((r) => r.limit === "200")).toBe(true);

  // Closing and reopening the drawer starts from the first page again, without fetching older targets.
  await page.keyboard.press("Escape");
  await page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Shopify stores: open runs" }).click();
  await expect(rows).toHaveCount(1 + 50);
  await expect(drawer.getByRole("button", { name: "Load more targets" })).toBeVisible();
  expect(seen.filter((r) => r.cursor !== null)).toHaveLength(loaded.length);
});

// imp-136 (aud-014 A14-05): the runs list ends in the same footer. 45 CJ runs, newest first: pages of 20, 20 and 5,
// each page's cursor the id of the run before it.
const CJ_RUNS = (url: URL) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj";
const cjRun = sources.find((s) => s.key === "cj")!.last_run!;
const cjRuns = Array.from({ length: 45 }, (_, i) => ({ ...cjRun, id: cjRun.id - i }));

async function pagedCjRuns(page: Page) {
  await page.route(CJ_RUNS, (route) => {
    const url = new URL(route.request().url());
    const cursor = Number(url.searchParams.get("cursor") ?? Infinity);
    const rest = cjRuns.filter((r) => r.id < cursor);
    const items = rest.slice(0, Number(url.searchParams.get("limit")));
    return route.fulfill({ json: { items, next_cursor: rest.length > items.length ? items.at(-1)!.id : null } });
  });
}

async function openCj(page: Page) {
  await page.goto(PAGE);
  await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
  const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
  return { drawer, runs: drawer.getByRole("list", { name: "CJ Dropshipping runs" }).getByRole("listitem") };
}

/** Every failure line in the drawer: a panel error, a stale line or a footer's. */
const errorLines = (drawer: Locator) => drawer.getByText(/^Couldn't (load|refresh)/);

for (const [width, height] of [
  [1440, 900],
  [375, 812],
]) {
  test(`runs at ${width}px: a failed older page keeps the loaded runs; its footer retries that page only, keeping focus`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await mockAdminApi(page);
    await pagedCjRuns(page);
    await fail(page, "/v1/admin/runs", String(cjRun.id - 19), 2); // the press and TanStack's one retry
    const seen = requests(page, /^\/api\/v1\/admin\/runs$/);
    const { drawer, runs } = await openCj(page);
    await expect(runs).toHaveCount(20);
    await expect(drawer).toContainText("Showing 20 runs · older runs not loaded yet");

    const more = drawer.getByRole("button", { name: /^(Load older runs|Loading…|Retry loading older runs)$/ });
    await expect(more).toHaveText("Load older runs");
    await more.focus();
    await page.keyboard.press("Enter");
    await expect(drawer).toContainText("Couldn't load older runs. The API is restarting. Try again. Error ID req-load-more");
    await expect(more).toHaveText("Retry loading older runs");
    await expect(more).toBeFocused();
    await expect(more).toBeInViewport({ ratio: 1 }); // the error line above didn't push it out of the drawer's view
    await expect(drawer.getByRole("button", { name: "Copy error ID" })).toBeVisible();
    await expect(runs).toHaveCount(20); // 20 of 20 kept
    await expect(errorLines(drawer)).toHaveCount(1); // at the foot only: no stale line above the list
    await expect(drawer.getByText("Showing data as of")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);

    await page.keyboard.press("Enter");
    await expect(runs).toHaveCount(40);
    await expect(more).toHaveText("Load older runs");
    await expect(more).toBeFocused();
    await expect(errorLines(drawer)).toHaveCount(0);

    await page.keyboard.press("Enter");
    await expect(runs).toHaveCount(45);
    await expect(more).toHaveCount(0);
    await expect(drawer.getByText("Showing all 45 runs")).toBeFocused();
    // The newest page once; then only the older pages, the failed one asked again by Retry.
    expect(seen.filter((r) => r.limit === "20")).toEqual([
      { cursor: null, limit: "20" },
      ...Array(3).fill({ cursor: String(cjRun.id - 19), limit: "20" }),
      { cursor: String(cjRun.id - 39), limit: "20" },
    ]);
  });
}

test("runs: a failed refresh of the newest page shows its line above the list once, and the footer stays as it was", async ({ page }) => {
  await mockAdminApi(page);
  await pagedCjRuns(page);
  const { drawer, runs } = await openCj(page);
  await expect(runs).toHaveCount(20);

  await page.route(CJ_RUNS, (route) => (new URL(route.request().url()).searchParams.get("cursor") ? route.fallback() : route.fulfill({ status: 503, json: problem(503, "req-runs-1") })));
  await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000)); // past the 5-minute staleTime
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange"))); // the tab refocuses: a refetch
  await expect(drawer.getByRole("group", { name: "Couldn't refresh runs" })).toContainText("Error ID req-runs-1");
  await expect(errorLines(drawer)).toHaveCount(1);
  await expect(runs).toHaveCount(20);
  await expect(drawer.getByRole("button", { name: "Load older runs" })).toBeVisible();
});

test("the runs list asks for its first page without a cursor", async ({ page }) => {
  await mockAdminApi(page);
  const seen = requests(page, /^\/api\/v1\/admin\/runs$/);
  await page.goto(PAGE);
  await page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "CJ Dropshipping: open runs" }).click();
  await expect(page.getByRole("dialog", { name: "CJ Dropshipping" }).getByRole("list", { name: "CJ Dropshipping runs" })).toBeVisible();
  // The API rejects cursor=0 (ge=1); the first page must omit it.
  expect(seen.filter((r) => r.limit === "20")).toEqual([{ cursor: null, limit: "20" }]);
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("the gap footer wraps with no horizontal page scroll", async ({ page }) => {
    await mockAdminApi(page, { gaps: manyGaps(260) });
    await page.goto(PAGE);
    const panel = page.getByRole("region", { name: "Coverage" });
    await panel.getByRole("button", { name: "Load older gaps" }).click();
    await expect(panel.getByRole("region", { name: "Open gaps" }).getByRole("row")).toHaveCount(1 + 250);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});
