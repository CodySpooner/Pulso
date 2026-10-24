import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, problem } from "./fixtures";

// imp-135 (aud-014 A14-04): a Retry the owner presses never leaves focus on the page. Success moves it to the
// restored panel's heading; a failure brings it back to Retry (also when the error left while refreshing) and is
// announced once, assertively. Refetches nobody pressed Retry for announce nothing and move no focus.

const PAGE = "/admin/data-health";
const API_DOWN = "The Pulso API didn't answer. When it runs on your PC, this also means the PC is off.";
const RESTARTING = "The API is restarting. Try again.";
const COVERAGE = "**/api/v1/admin/coverage**";

/** Live-region text a screen reader hears: a region whose text changes after it is inserted, or an alert inserted with text. */
async function recordAnnouncements(page: Page) {
  await page.addInitScript(() => {
    const heard: string[] = [];
    Object.assign(window, { heard });
    const seen = new WeakMap<Element, string>();
    new MutationObserver(() => {
      for (const el of document.querySelectorAll('[role="alert"], [role="status"], [aria-live]')) {
        const text = el.textContent?.trim() ?? "";
        const before = seen.get(el);
        seen.set(el, text);
        if (text && text !== before && (before !== undefined || el.getAttribute("role") === "alert")) heard.push(text);
      }
    }).observe(document, { subtree: true, childList: true, characterData: true });
  });
}
const announced = (page: Page) => page.evaluate(() => [...(window as unknown as { heard: string[] }).heard]);
const forget = (page: Page) => page.evaluate(() => void (window as unknown as { heard: string[] }).heard.splice(0));
const bodyFocused = (page: Page) => page.evaluate(() => document.activeElement === document.body);

/** Tab from the page's Refresh button (or `from`) until `target` has focus, as a keyboard user gets there. */
async function tabTo(page: Page, target: Locator, from = page.getByRole("button", { name: "Refresh" })) {
  await from.focus();
  for (let i = 0; i < 80 && !(await target.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(target).toBeFocused();
}

/** Every admin call fails without an answer (the API on the home PC is down) while `api.down` holds. */
async function apiDown(page: Page) {
  const api = { down: true };
  await page.route("**/api/v1/admin/**", (route) => (api.down ? route.abort("connectionrefused") : route.fallback()));
  return api;
}

/** The coverage call answers 503 while `cov.down` holds; `cov.calls` counts its requests. */
async function coverageDown(page: Page, down = true) {
  const cov = { down, calls: 0 };
  await page.route(COVERAGE, (route) => {
    cov.calls++;
    return cov.down ? route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }) : route.fallback();
  });
  return cov;
}

/** A background refetch: the tab becomes visible again, so TanStack refetches every query without data. */
const refocusTab = (page: Page) => page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));

for (const [width, height] of [
  [1440, 900],
  [375, 812],
]) {
  test.describe(`page-level Retry at ${width}px`, () => {
    test.use({ viewport: { width, height } });

    test("success: focus moves to the first restored panel's heading and nothing is announced", async ({ page }) => {
      await recordAnnouncements(page);
      await mockAdminApi(page);
      const api = await apiDown(page);
      await page.goto(PAGE);
      await expect(page.getByRole("heading", { level: 2, name: "Can't reach the API" })).toBeVisible();
      const retry = page.getByRole("button", { name: "Retry" });
      await tabTo(page, retry);
      await forget(page);

      api.down = false;
      await page.keyboard.press("Enter");
      const host = page.getByRole("heading", { level: 2, name: "Collector host" });
      await expect(host).toBeFocused();
      expect(await host.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none"); // a visible ring
      await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible(); // settled
      expect(await announced(page)).toEqual([]);
    });

    test("failure: the error leaves while refreshing, then focus returns to Retry and the failure is announced once", async ({ page }) => {
      await recordAnnouncements(page);
      await mockAdminApi(page);
      await apiDown(page);
      await page.goto(PAGE);
      const retry = page.getByRole("button", { name: "Retry" });
      await tabTo(page, retry);
      await forget(page);

      await page.keyboard.press("Enter");
      await expect(page.getByRole("button", { name: "Refreshing…" })).toBeVisible();
      await expect(retry).toHaveCount(0); // the error unmounted while refreshing
      await expect(retry).toBeFocused();
      await expect.poll(() => announced(page)).toEqual([`Can't reach the API. ${API_DOWN}`]);
      await page.waitForTimeout(500);
      expect(await announced(page)).toHaveLength(1);
      if (width === 375) expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    });
  });
}

test("coverage Retry success: focus moves to the Coverage heading and nothing is announced", async ({ page }) => {
  await recordAnnouncements(page);
  await mockAdminApi(page);
  const cov = await coverageDown(page);
  await page.goto(PAGE);
  const coverage = page.getByRole("region", { name: "Coverage" });
  await expect(coverage.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
  await tabTo(page, coverage.getByRole("button", { name: "Retry" }));
  await forget(page);

  cov.down = false;
  await page.keyboard.press("Enter");
  await expect(coverage.getByRole("heading", { level: 2, name: "Coverage" })).toBeFocused();
  await expect(coverage.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
  expect(await announced(page)).toEqual([]);
});

test("coverage Retry failure: focus returns to Retry, announced once; a later background refetch stays silent", async ({ page }) => {
  await recordAnnouncements(page);
  await mockAdminApi(page);
  const cov = await coverageDown(page);
  await page.goto(PAGE);
  const coverage = page.getByRole("region", { name: "Coverage" });
  const retry = coverage.getByRole("button", { name: "Retry" });
  await tabTo(page, retry);
  await forget(page);

  const before = cov.calls;
  await page.keyboard.press("Enter");
  await expect.poll(() => cov.calls).toBe(before + 2); // the press and TanStack's one retry
  await expect(retry).toBeFocused();
  await expect.poll(() => announced(page)).toEqual([`Couldn't load coverage. ${RESTARTING}`]);

  // Nothing pressed Retry for this refetch: it fails again without a word and leaves focus where it is (the page).
  await page.evaluate(() => (document.activeElement as HTMLElement).blur());
  await forget(page);
  const quiet = cov.calls;
  await refocusTab(page);
  await expect.poll(() => cov.calls).toBe(quiet + 2);
  await expect(retry).toBeVisible();
  await page.waitForTimeout(500);
  expect(await bodyFocused(page)).toBe(true);
  expect(await announced(page)).toEqual([]);
});

test("a refetch nobody pressed Retry for announces nothing and takes no focus (page-level error)", async ({ page }) => {
  await recordAnnouncements(page);
  await mockAdminApi(page);
  await apiDown(page);
  let calls = 0;
  await page.route("**/api/v1/admin/sources", (route) => {
    calls++;
    return route.abort("connectionrefused");
  });
  await page.goto(PAGE);
  await expect(page.getByRole("heading", { level: 2, name: "Can't reach the API" })).toBeVisible();
  expect(await announced(page)).toEqual([]); // the first load's failure isn't announced either
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

  const before = calls;
  await refocusTab(page);
  await expect.poll(() => calls).toBe(before + 2);
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.waitForTimeout(500);
  expect(await bodyFocused(page)).toBe(true);
  expect(await announced(page)).toEqual([]);
});

test("a stale panel's Retry: failure keeps focus and is announced once; success moves focus to the panel heading", async ({ page }) => {
  await recordAnnouncements(page);
  await mockAdminApi(page);
  const cov = await coverageDown(page, false);
  await page.goto(PAGE);
  const coverage = page.getByRole("region", { name: "Coverage" });
  await expect(coverage.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();

  cov.down = true;
  await page.getByRole("button", { name: "Refresh" }).click(); // the refetch fails; the cached heatmap stays
  const retry = coverage.getByRole("group", { name: "Couldn't refresh coverage" }).getByRole("button", { name: "Retry" });
  await tabTo(page, retry);
  await forget(page);

  await page.keyboard.press("Enter");
  await expect.poll(() => announced(page)).toEqual([`Couldn't refresh coverage. ${RESTARTING}`]);
  await expect(retry).toBeFocused();

  cov.down = false;
  await forget(page);
  await page.keyboard.press("Enter");
  await expect(coverage.getByRole("heading", { level: 2, name: "Coverage" })).toBeFocused();
  await expect(retry).toHaveCount(0);
  expect(await announced(page)).toEqual([]);
});

// imp-168: the run drawer is a retry scope too. Each failed press is announced once, like a panel's; success focuses
// the drawer's title. Focus never leaves the dialog, and a refetch nobody pressed Retry for stays silent there too.
for (const [what, failing] of [
  ["runs", (url: URL) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj"],
  ["targets", "**/api/v1/admin/runs/418"], // CJ's newest run, which opens expanded
] as const) {
  for (const [width, height] of [
    [1440, 900],
    [375, 812],
  ]) {
    test(`drawer Retry (${what}) at ${width}px: each failed press is announced once, success focuses the drawer title`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await recordAnnouncements(page);
      await mockAdminApi(page);
      const api = { down: true, calls: 0 };
      await page.route(failing, (route) => {
        api.calls++;
        return api.down ? route.fulfill({ status: 503, json: problem(503, "e2e-drawer-503") }) : route.fallback();
      });
      await page.goto(PAGE);
      await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
      const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
      const retry = drawer.getByRole("button", { name: "Retry" });
      await expect(drawer.getByRole("heading", { name: `Couldn't load ${what}` })).toBeVisible();
      expect(await announced(page)).toEqual([]); // the first load's failure is silent
      await tabTo(page, retry, drawer);

      // A second failed press, with focus already back on Retry (0 Tabs), is announced again.
      for (let press = 1; press <= 2; press++) {
        await forget(page);
        const before = api.calls;
        await page.keyboard.press("Enter");
        await expect.poll(() => api.calls).toBe(before + 2); // the press and TanStack's one retry
        await expect(retry).toBeFocused();
        await expect.poll(() => announced(page)).toEqual([`Couldn't load ${what}. ${RESTARTING}`]);
        await page.waitForTimeout(500);
        expect(await announced(page)).toHaveLength(1);
      }

      // Nothing pressed Retry for this refetch: silent, and focus stays on the dialog, where Radix leaves a lost one.
      await drawer.focus();
      await forget(page);
      const quiet = api.calls;
      await refocusTab(page);
      await expect.poll(() => api.calls).toBe(quiet + 2);
      await expect(retry).toBeVisible();
      await page.waitForTimeout(500);
      await expect(drawer).toBeFocused();
      expect(await announced(page)).toEqual([]);

      api.down = false;
      await tabTo(page, retry, drawer);
      await page.keyboard.press("Enter");
      const title = drawer.getByRole("heading", { level: 2, name: "CJ Dropshipping" });
      await expect(title).toBeFocused();
      expect(await title.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none"); // a visible ring
      await expect(what === "runs" ? drawer.getByRole("list", { name: "CJ Dropshipping runs" }) : drawer.getByRole("region", { name: "Run 418 targets" })).toBeVisible();
      expect(await announced(page)).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
}
