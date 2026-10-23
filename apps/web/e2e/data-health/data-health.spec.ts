import { expect, test, type Locator, type Page } from "@playwright/test";

import { healthySources, host, mockAdminApi, operationId, runDetail, sources, suppressedSources } from "./fixtures";

// DH-2 / DH-3 (P1-12): the Data Health page and nav badge against fixture DH-1 responses (E2E auth bypass).

const PAGE = "/admin/data-health";

async function open(page: Page) {
  await page.goto(PAGE);
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
}

/** The level of every heading in the accessibility tree, in document order. */
async function headingLevels(page: Page) {
  return page.getByRole("heading").evaluateAll((els) => els.map((el) => Number(el.getAttribute("aria-level") ?? el.tagName.slice(1))));
}

test("bounded pages disclose omitted rows and preserve overdue sources beyond the page", async ({ page }) => {
  const calls = await mockAdminApi(page, { host: { open_gaps: [host.open_gaps[2]], next_cursor: "fixture-next" } });
  await page.route("**/api/v1/admin/runs/412", (route) => route.fulfill({ json: { ...runDetail(412), next_cursor: "fixture-next" } }));
  await open(page);
  await expect(page.getByRole("region", { name: "Collector host" })).toContainText("At least 1 missed slots");
  await expect(page.getByText("Showing 1 range · 1 missed slot loaded, older gaps not loaded yet")).toBeVisible();
  const table = page.getByRole("region", { name: "Sources table" });
  await expect(table.getByRole("row", { name: /Google Trends/ })).toContainText("Overdue");
  await expect(page.getByRole("link", { name: /Data Health.*2 sources need attention/ }).first()).toBeVisible();
  await table.getByRole("button", { name: "Shopify stores: open runs" }).click();
  await expect(page.getByRole("dialog", { name: "Shopify stores" })).toContainText("Showing 4 of at least 5 targets");
  expect(calls.filter((c) => c.path === "/v1/admin/host")).toHaveLength(1);
});

test("renders every DH-1 field from fixtures", async ({ page }) => {
  await mockAdminApi(page);
  await open(page);
  await expect(page.getByText("As of Oct 22, 14:00 UTC")).toBeVisible();

  const hostCard = page.getByRole("region", { name: "Collector host" });
  await expect(hostCard).toContainText("pulso-pc");
  await expect(hostCard).toContainText("4m ago");
  await expect(hostCard).toContainText("Off here: live collectors run only on the collector host");
  await expect(hostCard).toContainText("3 missed slots · latest Google Trends");

  const backups = page.getByRole("region", { name: "Backups" });
  await expect(backups).toContainText("10h ago");
  await expect(backups).toContainText("1 of 14 failed");

  const table = page.getByRole("region", { name: "Sources table" });
  for (const [name, status] of [
    ["Shopify stores", "Blocked"],
    ["CJ Dropshipping", "Healthy"],
    ["Google Trends", "Overdue"],
    ["Frankfurter FX", "Disabled"],
  ]) {
    await expect(table.getByRole("row", { name: new RegExp(name) })).toContainText(status);
  }
  await expect(table).not.toContainText("Backups"); // the backup pseudo-source has its own card
  const cj = table.getByRole("row", { name: /CJ Dropshipping/ });
  await expect(cj).toContainText("1,240 / 36 / 112");
  await expect(cj).toContainText("as of 1h ago");
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("5 consecutive 429 responses");
  await expect(table.getByRole("row", { name: /Shopify stores/ })).toContainText("429");
  await expect(table.getByRole("row", { name: /Frankfurter FX/ })).toContainText("Not collected yet"); // missing, never 0
  await expect(table.getByRole("row", { name: /AliExpress/ })).toContainText("No source yet · arrives in Phase 3");

  await expect(page.getByRole("img", { name: /^Shopify stores, last 90 days/ })).toBeVisible();
  await expect(page.getByRole("img", { name: /^Google Trends, last 90 days: .*missed \(gap\)/ })).toBeVisible();
  const gaps = page.getByRole("region", { name: "Open gaps" });
  await expect(gaps.getByRole("row", { name: /Google Trends/ })).toContainText("Host offline");
  await expect(gaps.getByRole("row", { name: /Google Trends/ })).toContainText("2");
  await expect(page.locator("[data-scroll-cue]")).toHaveCount(0); // imp-069: every column fits, so no scroll cue
  await expect(page.getByRole("region", { name: "CSV import" }).getByLabel("Source")).toHaveValue("fx_frankfurter");

  // Run drawer: error text and raw-payload ids for the newest run, plus the source's remaining fields.
  await table.getByRole("button", { name: "Shopify stores: open runs" }).click();
  const drawer = page.getByRole("dialog", { name: "Shopify stores" });
  await expect(drawer).toContainText("429 Too Many Requests (retry-after 60)");
  await expect(drawer).toContainText("blocked_429");
  await expect(drawer).toContainText("#9001");
  await expect(drawer).toContainText("4 approved targets");
  await expect(drawer).toContainText("Retry not before");
  await expect(drawer.getByRole("button", { name: /#380/ })).toHaveAttribute("aria-expanded", "false");
});

test("a suppressed latest slot reads Skipped with its blocker, never Healthy (imp-042)", async ({ page }) => {
  await mockAdminApi(page, { sources: suppressedSources });
  await open(page);
  const table = page.getByRole("region", { name: "Sources table" });
  const cj = table.getByRole("row", { name: /CJ Dropshipping/ });
  await expect(cj).toContainText("Skipped");
  await expect(cj).toContainText("Run #419 was still active");
  await expect(cj).not.toContainText("Healthy");
  await expect(cj).toContainText("as of 1h ago"); // freshness stays the last success, not the skip
  // Controls keep their precedence.
  for (const [name, status] of [
    ["Shopify stores", "Blocked"],
    ["Google Trends", "Overdue"],
    ["Frankfurter FX", "Disabled"],
  ]) {
    await expect(table.getByRole("row", { name: new RegExp(name) })).toContainText(status);
  }
  // A skip isn't an alert by itself: the badge still counts only blocked, failing and overdue.
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ })).toHaveAccessibleName(
    /^Data Health\W+2 sources need attention$/,
  );

  await table.getByRole("button", { name: "CJ Dropshipping: open runs" }).click();
  const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
  await expect(drawer).toContainText("Skipped");
  // The newest run explains the skip as a warning, not as a failure.
  const reason = drawer.getByText("slot_suppressed").locator("..");
  await expect(reason).toContainText("slot_suppressed Run #419 was still active.");
  await expect(reason).toHaveClass(/bg-warning-muted/);
});

test("toggle and Run now call patch_source and run_source", async ({ page }) => {
  const calls = await mockAdminApi(page, { host: { live_runs_allowed: true } });
  await open(page);
  const table = page.getByRole("region", { name: "Sources table" });
  const writes = () => calls.filter((c) => c.method !== "GET");

  // Disabling a source asks for an optional reason.
  await table.getByRole("switch", { name: "CJ Dropshipping enabled" }).click();
  await page.getByRole("dialog", { name: "Disable CJ Dropshipping?" }).getByRole("textbox").fill("seed review");
  await page.getByRole("button", { name: "Disable", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "CJ Dropshipping disabled." })).toBeVisible();

  // Re-enabling a blocked source needs a typed reason (§4.2): an empty reason can't be submitted.
  await table.getByRole("switch", { name: "Shopify stores enabled" }).click();
  const reenable = page.getByRole("dialog", { name: "Re-enable Shopify stores?" });
  await reenable.getByRole("button", { name: "Re-enable" }).click();
  await expect(reenable).toBeVisible();
  await reenable.getByRole("textbox").fill("retry-after passed");
  await reenable.getByRole("button", { name: "Re-enable" }).click();
  await expect(reenable).toBeHidden();

  await table.getByRole("button", { name: "Run CJ Dropshipping now" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Run #500 queued for CJ Dropshipping." })).toBeVisible();

  expect(writes()).toEqual([
    { method: "PATCH", path: "/v1/admin/sources/cj", body: { enabled: false, reason: "seed review" } },
    { method: "PATCH", path: "/v1/admin/sources/shopify_stores", body: { enabled: true, reason: "retry-after passed" } },
    { method: "POST", path: "/v1/admin/sources/cj/run", body: null },
  ]);
  expect(writes().map((c) => operationId(c.method, c.path))).toEqual(["patch_source", "patch_source", "run_source"]);
});

test("Run now is unavailable off the collector host and says why", async ({ page }) => {
  const calls = await mockAdminApi(page);
  await open(page);
  const run = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Run CJ Dropshipping now" });
  await expect(run).toHaveAttribute("aria-disabled", "true");
  await run.focus();
  await expect(page.getByRole("tooltip")).toContainText("Live collectors run only on the collector host.");
  await run.click({ force: true }); // aria-disabled: Playwright would wait for it to enable
  expect(calls.filter((c) => c.method === "POST")).toEqual([]);
});

test("CSV import: keyboard to a file, row errors, one-click import, and a repeat is skipped", async ({ page }) => {
  const calls = await mockAdminApi(page);
  await open(page);
  const panel = page.getByRole("region", { name: "CSV import" });
  // Preselected: the one source with an import adapter (fixtures: Frankfurter FX).
  await expect(panel.getByLabel("Source")).toHaveValue("fx_frankfurter");
  await expect(panel.getByRole("link", { name: "Download template" })).toHaveAttribute("href", "/api/v1/admin/sources/fx_frankfurter/import/template");
  const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };

  // Action 1 (Enter on the focused button) opens the file picker; choosing the file checks it at once.
  await panel.getByRole("button", { name: "Choose CSV…" }).focus();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(file);
  await expect(panel.getByRole("region", { name: "Row errors" }).getByRole("row", { name: "5 rate Invalid rate. Use a finite positive decimal number below 10,000,000,000 with up to 8 decimal places." })).toBeVisible();
  await expect(panel).toContainText("3 valid");

  // Action 2 imports.
  await panel.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(panel).toContainText("Imported into Frankfurter FX as run #501: 3 new, 0 updated, 0 unchanged.");

  // The same bytes again: a skipped run pointing at the first.
  await panel.locator('input[type="file"]').setInputFiles(file);
  await panel.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(panel).toContainText("This exact file was already imported as run #501. Nothing new was written.");
  await panel.getByRole("button", { name: "Open runs" }).click();
  await expect(page.getByRole("dialog", { name: "Frankfurter FX" })).toBeVisible();
  await page.keyboard.press("Escape");

  // No import adapter yet: the file is checked again for the new source, and Import says why it's unavailable.
  await panel.locator('input[type="file"]').setInputFiles(file);
  await panel.getByLabel("Source").selectOption("cj");
  await expect(panel).toContainText("No import adapter yet");
  const blocked = panel.getByRole("button", { name: "Import 3 rows" });
  await expect(blocked).toHaveAttribute("aria-disabled", "true");
  await expect(blocked).toHaveAccessibleDescription(/importing into CJ Dropshipping arrives with its adapter/);

  const posts = calls.filter((c) => c.method === "POST");
  expect(posts.map((c) => operationId(c.method, c.path))).toEqual([
    "preview_import",
    "commit_source_import",
    "preview_import",
    "commit_source_import",
    "preview_import",
    "preview_import",
  ]);
  expect(posts.at(-1)?.path).toBe("/v1/admin/sources/cj/import/preview");
  expect(posts[0].body).toBe(file.buffer.toString()); // the raw bytes, not JSON or multipart
});

test.describe("DH-3 nav badge", () => {
  test("counts blocked, failing and overdue sources", async ({ page }) => {
    await mockAdminApi(page);
    await page.goto("/");
    const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
    await expect(link).toHaveAccessibleName(/^Data Health\W+2 sources need attention$/);
    await expect(link.getByTestId("data-health-badge")).toHaveText("2");
  });

  test("clears when no source needs attention", async ({ page }) => {
    await mockAdminApi(page, { sources: healthySources, host: { open_gaps: [], latest_gap_ends: {} } });
    await page.goto("/");
    const link = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: /Data Health/ });
    await expect(page.getByText("Online · 4m ago").first()).toBeVisible(); // data has loaded
    await expect(link).toHaveAccessibleName("Data Health");
    await expect(link.getByTestId("data-health-badge")).toHaveCount(0);
  });
});

test.describe("states", () => {
  test("loading shows skeletons, then content", async ({ page }) => {
    await mockAdminApi(page, { delayMs: 1500 });
    await open(page);
    await expect(page.getByRole("region", { name: "Sources", exact: true }).locator('[aria-hidden="true"].bg-skeleton').first()).toBeVisible();
    await expect(page.getByRole("button", { name: "CJ Dropshipping: open runs" }).first()).toBeVisible({ timeout: 10_000 });
  });

  test("API down replaces the page with one error", async ({ page }) => {
    await mockAdminApi(page, { down: true });
    await open(page);
    // imp-057: the page-level error is the h1's h2, so the outline never skips a level (axe heading-order).
    await expect(page.getByRole("heading", { level: 2, name: "Can't reach the API" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("When it runs on your PC, this also means the PC is off.")).toBeVisible();
    expect(await headingLevels(page)).toEqual([1, 2]);
  });

  test("a failed panel's error stays an h3 under its panel's h2", async ({ page }) => {
    await mockAdminApi(page);
    await page.route((url) => url.pathname === "/api/v1/admin/coverage", (route) => route.abort("connectionrefused"));
    await open(page);
    const coverage = page.getByRole("region", { name: "Coverage" });
    await expect(coverage.getByRole("heading", { level: 3, name: "Couldn't load coverage" })).toBeVisible({ timeout: 15_000 });
    const levels = await headingLevels(page);
    expect(levels.every((level, i) => i === 0 || level - levels[i - 1] <= 1)).toBe(true);
  });

  // imp-090 (aud-011 B11-05): the API-down h2 is set like the panel h2s it replaces (title-3, 600); an inline
  // panel error's h3 keeps its body/500 title. Both tokens step up 1px under 640px.
  for (const theme of ["dark", "light"] as const) {
    for (const [width, title3, body] of [
      [1440, "15px", "14px"],
      [375, "16px", "15px"],
    ] as const) {
      test(`error titles at ${width}px ${theme}`, async ({ page }) => {
        const font = (heading: Locator) => heading.evaluate((el) => `${getComputedStyle(el).fontSize}/${getComputedStyle(el).fontWeight}`);
        const noHScroll = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme: theme });
        await page.addInitScript((t) => localStorage.setItem("theme", t), theme);

        await mockAdminApi(page, { down: true });
        await open(page);
        const apiDown = page.getByRole("heading", { level: 2, name: "Can't reach the API" });
        await expect(apiDown).toBeVisible({ timeout: 15_000 });
        expect(await font(apiDown)).toBe(`${title3}/600`);
        expect(await noHScroll()).toBe(true);

        await mockAdminApi(page); // newer routes win: the API is back, only coverage fails
        await page.route((url) => url.pathname === "/api/v1/admin/coverage", (route) => route.abort("connectionrefused"));
        await open(page);
        const coverage = page.getByRole("region", { name: "Coverage" });
        await expect(coverage.getByRole("heading", { level: 3, name: "Couldn't load coverage" })).toBeVisible({ timeout: 15_000 });
        expect(await font(coverage.getByRole("heading", { level: 3 }))).toBe(`${body}/500`);
        expect(await font(coverage.getByRole("heading", { level: 2 }))).toBe(`${title3}/600`);
        expect(await noHScroll()).toBe(true);
      });
    }
  }

  test("no sources configured", async ({ page }) => {
    await mockAdminApi(page, { sources: [], coverage: [] });
    await open(page);
    await expect(page.getByRole("heading", { name: "No sources configured" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "No coverage yet" })).toBeVisible();
  });

  test("an offline host is flagged at the top", async ({ page }) => {
    await mockAdminApi(page, { host: { latest_heartbeat: { host: "pulso-pc", at: "2026-10-22T11:00:00Z" } } });
    await open(page);
    await expect(page.getByText("Collector host offline")).toBeVisible();
    await expect(page.getByRole("region", { name: "Collector host" })).toContainText("Offline");
  });
});

test("keyboard: open a source's runs and close them again", async ({ page }) => {
  await mockAdminApi(page);
  await open(page);
  const name = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "CJ Dropshipping: open runs" });
  for (let i = 0; i < 40 && !(await name.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(name).toBeFocused();
  expect(await name.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "CJ Dropshipping" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(name).toBeFocused();
});

// imp-073: a status pill's hint opens on keyboard focus, not just on hover.
test("keyboard: every status pill shows its hint on focus", async ({ page }) => {
  await mockAdminApi(page);
  await open(page);
  const table = page.getByRole("region", { name: "Sources table" });
  for (const [name, status, hint] of [
    ["Shopify stores", "Blocked", "The block rule tripped and the adapter turned itself off (§4.2)."],
    ["CJ Dropshipping", "Healthy", "The last run succeeded."],
    ["Google Trends", "Overdue", "A scheduled run in the last 24 h was missed and not caught up."],
    ["Frankfurter FX", "Disabled", "Disabled by the owner. Nothing is collected."],
  ]) {
    await table.getByRole("button", { name: `${name}: open runs` }).focus();
    await page.keyboard.press("Tab");
    const pill = table.getByRole("row", { name: new RegExp(name) }).getByRole("button", { name: status, exact: true });
    await expect(pill).toBeFocused();
    expect(await pill.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
    await expect(page.getByRole("tooltip", { name: hint })).toBeVisible();
    await expect(pill).toHaveAccessibleDescription(hint);
  }
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);

  // Opening the drawer focuses the drawer, not its pill, so no hint pops open uninvited; Tab reaches it.
  await table.getByRole("button", { name: "CJ Dropshipping: open runs" }).click();
  const drawer = page.getByRole("dialog", { name: "CJ Dropshipping" });
  await expect(drawer).toBeFocused();
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await page.keyboard.press("Tab");
  await expect(drawer.getByRole("button", { name: "Healthy", exact: true })).toBeFocused();
  await expect(page.getByRole("tooltip", { name: "The last run succeeded." })).toBeVisible();
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test.describe("touch", () => {
    test.use({ hasTouch: true });

    test("a tap toggles a status hint, and an open hint never blocks a control (imp-073)", async ({ page }) => {
      await mockAdminApi(page, { sources: suppressedSources });
      await open(page);
      const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "CJ Dropshipping: open runs" }) });
      const pill = card.getByRole("button", { name: "Skipped", exact: true });
      const hint = page.getByRole("tooltip");

      await pill.tap();
      await expect(hint).toContainText("The latest slot was skipped while an earlier run of the same job was active");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
      // The hint is click-through: whatever it covers still takes the tap.
      const box = (await page.locator("[data-radix-popper-content-wrapper]").boundingBox())!;
      const under = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest("[data-radix-popper-content-wrapper]") ?? null, [box.x + box.width / 2, box.y + box.height / 2]);
      expect(under).toBeNull();
      await pill.tap();
      await expect(hint).toBeHidden();

      // An open hint doesn't swallow the next action: one tap on the switch opens its dialog and closes the hint.
      await pill.tap();
      await expect(hint).toBeVisible();
      await card.getByRole("switch", { name: "CJ Dropshipping enabled" }).tap();
      await expect(page.getByRole("dialog", { name: "Disable CJ Dropshipping?" })).toBeVisible();
      await expect(hint).toBeHidden();
    });
  });

  test("cards replace the table with no horizontal page scroll", async ({ page }) => {
    await mockAdminApi(page);
    await open(page);
    await expect(page.getByRole("switch", { name: "CJ Dropshipping enabled" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Sources table" })).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });

  test("open gaps cue hidden columns and scroll to them by keyboard (imp-069)", async ({ page }) => {
    await mockAdminApi(page);
    await open(page);
    const gaps = page.getByRole("region", { name: "Open gaps" });
    const cue = (side: string) => page.locator(`[data-scroll-cue="${side}"]`);
    await expect(cue("right")).toBeVisible();
    await expect(cue("left")).toHaveCount(0);
    await expect(gaps.getByRole("columnheader", { name: "Reason" })).not.toBeInViewport();

    await gaps.focus();
    for (let i = 0; i < 12; i++) await page.keyboard.press("ArrowRight");
    await expect(gaps.getByRole("columnheader", { name: "Reason" })).toBeInViewport();
    await expect(cue("right")).toHaveCount(0);
    await expect(cue("left")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });

  test("a suppressed slot's card says Skipped and why (imp-042)", async ({ page }) => {
    await mockAdminApi(page, { sources: suppressedSources });
    await open(page);
    const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "CJ Dropshipping: open runs" }) });
    await expect(card).toContainText("Skipped");
    await expect(card).toContainText("Run #419 was still active");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});

// imp-093: at 768–1023px the sidebar is hidden and there is no tab bar, so the top bar's Open menu carries the DH-3 count.
for (const width of [768, 1023]) {
  test.describe(`tablet ${width}px`, () => {
    test.use({ viewport: { width, height: 1024 } });
    const menuButton = (page: Page) => page.getByRole("banner").getByRole("button", { name: /^Open menu/ });

    test("Open menu shows the DH-3 count before the sheet opens", async ({ page }) => {
      await mockAdminApi(page);
      await page.goto("/");
      const menu = menuButton(page);
      await expect(menu).toHaveAccessibleName(/^Open menu\W+2 sources need attention$/);
      await expect(menu.getByTestId("data-health-badge")).toBeVisible();
      await expect(menu.getByTestId("data-health-badge")).toHaveText("2");
      await expect(page.getByText(/need attention/).filter({ visible: true })).toHaveCount(1); // the hidden sidebar's copy isn't announced
      await menu.click();
      await expect(page.getByRole("dialog").getByRole("link", { name: /Data Health/ })).toHaveAccessibleName(/^Data Health\W+2 sources need attention$/);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });

    test("Open menu shows nothing when no source needs attention", async ({ page }) => {
      await mockAdminApi(page, { sources: healthySources, host: { open_gaps: [], latest_gap_ends: {} } });
      await page.goto("/");
      await expect(page.getByText("Online · 4m ago").first()).toBeAttached(); // data has loaded
      await expect(menuButton(page)).toHaveAccessibleName("Open menu");
      await expect(menuButton(page).getByTestId("data-health-badge")).toHaveCount(0);
    });

    test("Open menu shows nothing while the API is down", async ({ page }) => {
      await mockAdminApi(page, { down: true });
      await page.goto(PAGE);
      await expect(page.getByRole("heading", { level: 2, name: "Can't reach the API" })).toBeVisible({ timeout: 15_000 });
      await expect(menuButton(page)).toHaveAccessibleName("Open menu");
    });
  });
}

// Keeps the fixture honest: the overdue source comes from an open gap, not from a status field.
test("fixture sanity", () => {
  expect(sources.find((s) => s.key === "google_trends")?.status).toBe("active");
  expect(host.open_gaps.some((g) => g.source_key === "google_trends")).toBe(true);
  // imp-042: CJ's only open gap is days old, so nothing but the skip can keep it off Healthy.
  expect(host.open_gaps.filter((g) => g.source_key === "cj").every((g) => Date.parse(g.slot_end) < Date.parse("2026-10-21T14:00:00Z"))).toBe(true);
});
