import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, NOW, offlineNetwork, problem, sources } from "./fixtures";

// imp-173, imp-155, imp-175 (DEC-232): a press opens or keeps a TapTooltip's reason and never closes it; one reason
// is open at a time, whatever opened it; a Retry's reason sits below it, clear of the Error ID line. imp-154,
// imp-186, imp-187 (DEC-235): each offline reason names its action, and an open reason covers no content.

/** Reasons open now. A closing one keeps its role while it fades, so count by state. */
const openReasons = (page: Page) => page.locator('[role="tooltip"][data-state$="-open"]');
const isOpen = (control: Locator) => expect(control).toHaveAttribute("data-state", /-open$/);
const isClosed = (control: Locator) => expect(control).toHaveAttribute("data-state", "closed");
/** From now on, records every state `control`'s reason passes through; `seenStates` reads them. */
const watchState = (control: Locator) =>
  control.evaluate((el) => {
    const seen: string[] = [];
    new MutationObserver(() => seen.push(el.dataset.state ?? "")).observe(el, { attributeFilter: ["data-state"] });
    (window as unknown as { seen: string[] }).seen = seen;
  });
const seenStates = (page: Page) => page.evaluate(() => (window as unknown as { seen: string[] }).seen);
/** The text, icons, switches and chart cells inside `scope` that the one open reason covers: none when it's clear. */
async function underReason(page: Page, scope: Locator) {
  const reason = openReasons(page);
  await expect(reason).toHaveCount(1);
  await expect(reason).toBeVisible();
  const r = (await reason.boundingBox())!;
  const covered = await scope.evaluate((root, r) => {
    const hit = (b: DOMRect) => b.width > 0 && b.height > 0 && b.left < r.x + r.width && r.x < b.right && b.top < r.y + r.height && r.y < b.bottom;
    const out: string[] = [];
    const text = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = text.nextNode(); n; n = text.nextNode()) {
      if (!n.textContent!.trim() || n.parentElement!.closest(".sr-only")) continue;
      const words = document.createRange(); // the words' own boxes, not their block's
      words.selectNodeContents(n);
      if (Array.from(words.getClientRects()).some(hit)) out.push(n.textContent!.trim());
    }
    for (const el of root.querySelectorAll("svg, [role=img] > *, [role=switch]")) if (hit(el.getBoundingClientRect())) out.push(el.getAttribute("title") ?? el.tagName);
    return out;
  }, r);
  return { covered, reason: r };
}
const bottomOf = async (el: Locator) => {
  const b = (await el.boundingBox())!;
  return b.y + b.height;
};

async function coverageDown(page: Page) {
  await page.route("**/api/v1/admin/coverage**", (route) => route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }));
}

test("a press on a locked control keeps its reason: Enter or Space after focus, a click after hover (imp-173)", async ({ page, context }) => {
  const calls = await mockAdminApi(page);
  await coverageDown(page);
  const { offlineCalls, setOffline } = await offlineNetwork(page, context);
  await page.goto("/admin/data-health");
  const table = page.getByRole("region", { name: "Sources table" });
  const coverage = page.getByRole("region", { name: "Coverage" });
  await expect(coverage.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
  await setOffline(true);

  const offline = (action: string) => `You're offline. Reconnect to ${action}.`; // names its action (imp-154)
  for (const [control, reason] of [
    [page.getByRole("button", { name: "Refresh" }), offline("refresh")],
    [table.getByRole("switch", { name: "CJ Dropshipping enabled" }), offline("disable CJ Dropshipping")],
    [table.getByRole("button", { name: "Run CJ Dropshipping now" }), "Live collectors run only on the collector host."], // a reason that outlasts offline comes first
    [page.getByRole("region", { name: "CSV import" }).getByRole("button", { name: "Choose CSV…" }), offline("choose a CSV for Frankfurter FX")],
    [coverage.getByRole("button", { name: "Retry" }), offline("retry")],
  ] as const) {
    await expect(control).toHaveAttribute("aria-disabled", "true");
    await control.focus(); // by keyboard: the reason opens on focus
    await isOpen(control);
    await expect(control).toHaveAccessibleDescription(reason);
    for (const key of ["Enter", " ", "Enter"]) {
      await page.keyboard.press(key);
      await isOpen(control);
      await expect(openReasons(page)).toHaveCount(1);
    }
    await expect(control).toBeFocused();
    await page.keyboard.press("Escape"); // Escape still closes it
    await isClosed(control);
    await page.keyboard.press("Enter"); // and a press brings it back
    await isOpen(control);
    await control.blur(); // so does losing focus
    await isClosed(control);

    await control.hover();
    await isOpen(control);
    await watchState(control); // the reason must not close on pointerdown and reopen on the click
    await control.click({ force: true }); // force: aria-disabled, so Playwright would wait for it to enable
    await isOpen(control);
    await control.click({ force: true });
    await isOpen(control);
    expect(await seenStates(page)).not.toContain("closed");
    await page.mouse.move(0, 0, { steps: 5 }); // the pointer leaving still closes it
    await isClosed(control);
    await control.blur();
  }
  expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
  expect(offlineCalls).toEqual([]);
});

test.describe("one reason at a time (imp-155)", () => {
  /** A locked control and a status pill, each with its own reason. */
  const controls = (page: Page) => {
    const table = page.getByRole("region", { name: "Sources table" });
    return { run: table.getByRole("button", { name: "Run CJ Dropshipping now" }), pill: table.getByRole("button", { name: "Healthy", exact: true }) };
  };

  test("a reason opened by keyboard closes one open on hover", async ({ page }) => {
    await mockAdminApi(page);
    await page.goto("/admin/data-health");
    const { run, pill } = controls(page);
    await run.focus();
    await page.keyboard.press("Escape"); // focused, its reason closed
    await pill.hover();
    await isOpen(pill);
    await page.keyboard.press("Enter"); // the pointer still rests on the pill
    await isOpen(run);
    await isClosed(pill);
    await expect(openReasons(page)).toHaveCount(1);

    await page.keyboard.press("Escape");
    await page.mouse.move(0, 0, { steps: 5 });
    await pill.hover();
    await isOpen(pill);
    await page.keyboard.press(" ");
    await isOpen(run);
    await expect(openReasons(page)).toHaveCount(1);
  });

  test("a reason opened by click or hover closes one open on keyboard focus", async ({ page }) => {
    await mockAdminApi(page);
    await page.goto("/admin/data-health");
    const { run, pill } = controls(page);
    await run.focus();
    await isOpen(run);
    await pill.click();
    await isOpen(pill);
    await expect(openReasons(page)).toHaveCount(1);

    await page.mouse.move(0, 0, { steps: 5 }); // first: a pointer passing over another trigger opens its reason
    await run.focus();
    await isOpen(run);
    await pill.hover();
    await isOpen(pill);
    await expect(openReasons(page)).toHaveCount(1);
  });

  test.describe("touch", () => {
    test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

    test("a tapped reason closes the one open before it", async ({ page }) => {
      await mockAdminApi(page);
      await page.goto("/admin/data-health");
      const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "CJ Dropshipping: open runs" }) });
      const run = card.getByRole("button", { name: "Run CJ Dropshipping now" });
      const pill = card.getByRole("button", { name: "Healthy", exact: true });
      await run.tap({ force: true });
      await isOpen(run);
      await pill.tap();
      await isOpen(pill);
      await expect(openReasons(page)).toHaveCount(1);
      await watchState(pill);
      await pill.tap(); // a second tap keeps it (imp-173), without closing in between
      await isOpen(pill);
      await page.waitForTimeout(300);
      expect(await seenStates(page)).toEqual([]);
      await page.getByRole("heading", { level: 1 }).tap(); // a tap elsewhere closes it
      await expect(openReasons(page)).toHaveCount(0);
    });
  });
});

for (const [width, height] of [
  [1440, 900],
  [375, 812],
] as const) {
  test(`${width}px: a Retry's reason covers neither the Error ID line nor what the line sits on (imp-175, imp-186)`, async ({ page, context }) => {
    await page.setViewportSize({ width, height });
    const cov = { down: false };
    await mockAdminApi(page);
    await page.route("**/api/v1/admin/coverage**", (route) => (cov.down ? route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }) : route.fallback()));
    const { setOffline } = await offlineNetwork(page, context);
    await page.goto("/admin/data-health");
    const coverage = page.getByRole("region", { name: "Coverage" });
    await expect(coverage.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();

    // A stale line: the refetch failed, the chart stays. Wide, Retry shares the message's row, so the reason sits
    // above it, over the empty panel header; on a phone the actions wrap below the Error ID, so it sits on their
    // row's empty left (DEC-235 b). Either way it covers nothing of the panel: the Error ID, the chart or a label.
    cov.down = true;
    await page.getByRole("button", { name: "Refresh" }).click();
    const stale = coverage.getByRole("group", { name: "Couldn't refresh coverage" });
    await expect(stale).toBeVisible();
    await setOffline(true);
    const retry = stale.getByRole("button", { name: "Retry" });
    await retry.focus();
    const { covered, reason } = await underReason(page, coverage);
    expect(covered).toEqual([]);
    const b = (await retry.boundingBox())!;
    if (width === 1440) expect(reason.y + reason.height).toBeLessThanOrEqual(b.y);
    else expect(reason.x + reason.width).toBeLessThanOrEqual(b.x);
    await retry.blur();

    // A panel error: the first load failed. The Error ID line sits over Retry at every width, so the reason is below.
    await setOffline(false);
    await page.reload();
    await expect(coverage.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
    await setOffline(true);
    const panelRetry = coverage.getByRole("button", { name: "Retry" });
    await panelRetry.focus();
    const panel = await underReason(page, coverage);
    expect(panel.covered).toEqual([]);
    expect(panel.reason.y).toBeGreaterThanOrEqual(await bottomOf(panelRetry));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });

  test(`${width}px: the run drawer's stale-line Retry reason covers nothing in the drawer (imp-186)`, async ({ page, context }) => {
    await page.setViewportSize({ width, height });
    const cjRun = sources.find((s) => s.key === "cj")!.last_run!;
    const runs = { down: false };
    await mockAdminApi(page);
    await page.route(
      (url) => url.pathname === "/api/v1/admin/runs" && url.searchParams.get("source") === "cj",
      (route) =>
        runs.down
          ? route.fulfill({ status: 503, json: problem(503, "req-runs-1") })
          : route.fulfill({ json: { items: [cjRun], next_cursor: String(cjRun.id) } }),
    );
    const { setOffline } = await offlineNetwork(page, context);
    await page.goto("/admin/data-health");
    await page.getByRole("button", { name: "CJ Dropshipping: open runs" }).locator("visible=true").click();
    const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
    await expect(drawer.getByRole("button", { name: "Load older runs" })).toBeVisible();
    // The drawer's stale line is a failed refresh of the loaded runs; an older page fails at the list's foot (DEC-236 a).
    runs.down = true;
    await page.clock.setFixedTime(new Date(NOW.getTime() + 6 * 60_000)); // past the 5-minute staleTime
    await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange"))); // the tab refocuses: a refetch
    const stale = drawer.getByRole("group", { name: "Couldn't refresh runs" });
    await expect(stale).toBeVisible();
    await setOffline(true);
    // The drawer is narrow at every width, so its actions wrap onto their own row: the reason sits on its empty
    // left, clear of the Error ID above and the first run below.
    const retry = stale.getByRole("button", { name: "Retry" });
    await retry.focus();
    const { covered, reason } = await underReason(page, drawer);
    expect(covered).toEqual([]);
    expect(reason.x + reason.width).toBeLessThanOrEqual((await retry.boundingBox())!.x);
  });
}

test.describe("phone cards", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  test("375px: a phone card's Run now reason sits below its controls, clear of its card and the next (imp-187)", async ({ page }) => {
    await mockAdminApi(page);
    await page.goto("/admin/data-health");
    const list = page.getByRole("list").filter({ has: page.getByRole("button", { name: "CJ Dropshipping: open runs" }) });
    const run = list.getByRole("button", { name: "Run CJ Dropshipping now" });
    await run.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await run.tap({ force: true });
    await isOpen(run);
    const { covered, reason } = await underReason(page, list);
    expect(covered).toEqual([]); // above, it covered the card's Freshness line
    expect(reason.y).toBeGreaterThanOrEqual(await bottomOf(run));
  });
});

test("1440px: the table's Run now reason still sits above it (imp-187)", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto("/admin/data-health");
  const run = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Run CJ Dropshipping now" });
  await run.focus();
  await isOpen(run);
  expect(await bottomOf(openReasons(page))).toBeLessThanOrEqual((await run.boundingBox())!.y);
});
