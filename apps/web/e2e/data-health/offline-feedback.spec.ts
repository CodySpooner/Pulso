import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, offlineNetwork, problem } from "./fixtures";

// imp-153, imp-157 (imp-134 leftovers 1 and 5). Offline, a check or import that fails names the connection instead
// of blaming the API, and a Retry on a stale line or a panel error is locked with the offline reason instead of
// waiting silently for the connection. Reconnecting still refetches by itself.

const PAGE = "/admin/data-health";
const OFFLINE_CHECK = "You're offline. Retry once you reconnect.";
const OFFLINE_IMPORT = "You're offline. Retry once you reconnect; a retry never imports the same file twice.";
const BLAMES_API = /didn't answer/;
const HINT = "You're offline. Reconnect to use this.";
const PREVIEW = /\/api\/v1\/admin\/sources\/[^/]+\/import\/preview$/;
const COMMIT = /\/api\/v1\/admin\/sources\/[^/]+\/import$/;
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

/** Holds `pattern`'s next request until the returned release, then fails it the way an offline Chromium does. */
async function cutOff(page: Page, pattern: RegExp) {
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(
    pattern,
    async (route) => {
      await held;
      await route.abort("internetdisconnected");
    },
    { times: 1 },
  );
  return release;
}

/** The coverage call answers 503 while `cov.down` holds; `cov.calls` counts the requests that reach it. */
async function coverageDown(page: Page, down: boolean) {
  const cov = { down, calls: 0 };
  await page.route("**/api/v1/admin/coverage**", (route) => {
    cov.calls++;
    return cov.down ? route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }) : route.fallback();
  });
  return cov;
}

/**
 * Presses a locked Retry and checks the press says why: a tap opens the reason (imp-126); on a desktop keyboard
 * focus opens it, and so does a click. force: aria-disabled, so Playwright would wait for it to enable.
 */
async function pressOffline(retry: Locator, touch: boolean) {
  const saysWhy = async () => {
    await expect(retry).toHaveAttribute("aria-disabled", "true");
    await expect(retry).toHaveAccessibleDescription(HINT);
    await expect(retry.page().getByRole("tooltip", { name: HINT }).first()).toBeVisible();
  };
  if (touch) {
    await retry.tap({ force: true });
    await saysWhy();
    return;
  }
  await retry.focus();
  await saysWhy();
  await retry.blur();
  await retry.click({ force: true });
  await saysWhy();
}

test("a check and an import cut off by the connection, and a check started offline, say offline", async ({ page, context }) => {
  await mockAdminApi(page);
  const { offlineCalls, setOffline } = await offlineNetwork(page, context);
  await page.goto(PAGE);
  const banner = page.getByRole("status").filter({ hasText: "You're offline." });
  const panel = page.getByRole("region", { name: "CSV import" });
  const alert = panel.getByRole("alert");
  /** The visible error line, not the sr-only alert that speaks it. */
  const line = (text: string) => panel.getByText(text, { exact: true }).and(panel.locator(":not([role=alert])"));

  // A check in flight when the connection drops.
  const releaseCheck = await cutOff(page, PREVIEW);
  await panel.locator('input[type="file"]').setInputFiles(file);
  await expect(panel.getByRole("status")).toHaveText("Checking rates.csv…");
  await setOffline(true);
  await expect(banner).toBeVisible();
  releaseCheck();
  await expect(line(OFFLINE_CHECK)).toBeVisible();
  await expect(alert).toHaveText(OFFLINE_CHECK); // already names Retry, so no "Select Retry to try again."
  await expect(panel).not.toContainText(BLAMES_API);

  // The Source select checks the open file again at once: offline, that check fails the same way.
  await panel.getByLabel("Source").selectOption("cj");
  await expect.poll(() => offlineCalls).toEqual(["POST /api/v1/admin/sources/cj/import/preview"]);
  await expect(panel.getByText("checked against the CJ Dropshipping template")).toBeVisible();
  await expect(line(OFFLINE_CHECK)).toBeVisible();
  await expect(panel).not.toContainText(BLAMES_API);

  // Back online the file checks, then an import in flight when the connection drops says so too.
  await setOffline(false);
  await panel.getByLabel("Source").selectOption("fx_frankfurter");
  const importButton = panel.getByRole("button", { name: "Import 3 rows" });
  await expect(importButton).not.toHaveAttribute("aria-disabled", "true");
  const releaseImport = await cutOff(page, COMMIT);
  await importButton.click();
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
  await setOffline(true);
  await expect(banner).toBeVisible();
  releaseImport();
  await expect(line(OFFLINE_IMPORT)).toBeVisible();
  await expect(alert).toHaveText(OFFLINE_IMPORT);
  await expect(panel).not.toContainText(BLAMES_API);

  // The failure keeps its cause after reconnecting: it happened offline.
  await setOffline(false);
  await expect(banner).toHaveCount(0);
  await expect(line(OFFLINE_IMPORT)).toBeVisible();
});

for (const [width, height] of [
  [1440, 900],
  [375, 812],
] as const) {
  test.describe(`${width}px`, () => {
    const touch = width < 768;
    test.use({ viewport: { width, height }, hasTouch: touch });

    test("a stale line's Retry offline says why and sends nothing; reconnecting still refetches", async ({ page, context }) => {
      await mockAdminApi(page);
      const cov = await coverageDown(page, false);
      const { offlineCalls, setOffline } = await offlineNetwork(page, context);
      await page.goto(PAGE);
      const panel = page.getByRole("region", { name: "Coverage" });
      const heatmap = panel.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ });
      await expect(heatmap).toBeVisible();

      cov.down = true;
      await page.getByRole("button", { name: "Refresh" }).click(); // the refetch fails; the cached heatmap stays
      const stale = panel.getByRole("group", { name: "Couldn't refresh coverage" });
      const retry = stale.getByRole("button", { name: "Retry" });
      await expect(retry).toBeVisible();
      await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible(); // settled
      await setOffline(true);

      await pressOffline(retry, touch);
      await expect(retry).toBeFocused();
      await expect(stale.getByRole("alert")).toHaveText(""); // nothing failed, so nothing is announced
      expect(offlineCalls).toEqual([]);

      // Reconnect: the background refetch runs by itself, as before, and the line goes.
      cov.down = false;
      const before = cov.calls;
      await setOffline(false);
      await expect.poll(() => cov.calls).toBeGreaterThan(before);
      await expect(stale).toHaveCount(0);
      await expect(heatmap).toBeVisible();
    });

    test("a panel error's Retry offline says why and sends nothing; reconnecting still refetches", async ({ page, context }) => {
      await mockAdminApi(page);
      const cov = await coverageDown(page, true);
      const { offlineCalls, setOffline } = await offlineNetwork(page, context);
      await page.goto(PAGE);
      const panel = page.getByRole("region", { name: "Coverage" });
      const retry = panel.getByRole("button", { name: "Retry" });
      await expect(panel.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
      await setOffline(true);

      await pressOffline(retry, touch);
      await expect(retry).toBeFocused();
      await expect(panel.getByRole("alert")).toHaveText("");
      expect(offlineCalls).toEqual([]);
      if (touch) expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      cov.down = false;
      const before = cov.calls;
      await setOffline(false);
      await expect.poll(() => cov.calls).toBeGreaterThan(before);
      await expect(panel.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();
    });
  });
}
