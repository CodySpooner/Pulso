import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, offlineNetwork, problem } from "./fixtures";

// imp-173, imp-155, imp-175 (DEC-232): a press opens or keeps a TapTooltip's reason and never closes it; one reason
// is open at a time, whatever opened it; a Retry's reason sits below it, clear of the Error ID line.

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

  for (const control of [
    page.getByRole("button", { name: "Refresh" }),
    table.getByRole("switch", { name: "CJ Dropshipping enabled" }),
    table.getByRole("button", { name: "Run CJ Dropshipping now" }),
    page.getByRole("region", { name: "CSV import" }).getByRole("button", { name: "Choose CSV…" }),
    coverage.getByRole("button", { name: "Retry" }),
  ]) {
    await expect(control).toHaveAttribute("aria-disabled", "true");
    await control.focus(); // by keyboard: the reason opens on focus
    await isOpen(control);
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
  test(`${width}px: a Retry's reason sits below it, clear of the Error ID line (imp-175)`, async ({ page, context }) => {
    await page.setViewportSize({ width, height });
    const cov = { down: false };
    await mockAdminApi(page);
    await page.route("**/api/v1/admin/coverage**", (route) => (cov.down ? route.fulfill({ status: 503, json: problem(503, "e2e-cov-503") }) : route.fallback()));
    const { setOffline } = await offlineNetwork(page, context);
    await page.goto("/admin/data-health");
    const coverage = page.getByRole("region", { name: "Coverage" });
    await expect(coverage.getByRole("img", { name: /^CJ Dropshipping, last 90 days/ })).toBeVisible();

    /** Keyboard focus on `retry` opens its reason, which must clear the Error ID line and sit under the button. */
    const clearOfErrorId = async (retry: Locator, errorId: Locator) => {
      await retry.focus();
      const reason = openReasons(page);
      await expect(reason).toHaveCount(1);
      await expect(reason).toBeVisible();
      const [r, id, b] = [(await reason.boundingBox())!, (await errorId.boundingBox())!, (await retry.boundingBox())!];
      const overlaps = r.x < id.x + id.width && id.x < r.x + r.width && r.y < id.y + id.height && id.y < r.y + r.height;
      expect(overlaps, `reason ${JSON.stringify(r)} vs Error ID ${JSON.stringify(id)}`).toBe(false);
      expect(r.y).toBeGreaterThanOrEqual(b.y + b.height);
      await retry.blur();
    };

    // A stale line: the refetch failed, the chart stays.
    cov.down = true;
    await page.getByRole("button", { name: "Refresh" }).click();
    const stale = coverage.getByRole("group", { name: "Couldn't refresh coverage" });
    await expect(stale).toBeVisible();
    await setOffline(true);
    await clearOfErrorId(stale.getByRole("button", { name: "Retry" }), stale.getByText(/^Error ID/));

    // A panel error: the first load failed.
    await setOffline(false);
    await page.reload();
    await expect(coverage.getByRole("heading", { name: "Couldn't load coverage" })).toBeVisible();
    await setOffline(true);
    await clearOfErrorId(coverage.getByRole("button", { name: "Retry" }), coverage.locator("span.font-mono", { hasText: "Error ID" }));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  });
}
