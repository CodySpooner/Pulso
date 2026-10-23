import { expect, test, type Locator, type Page, type Route } from "@playwright/test";

import { mockAdminApi, problem, sources, type MockOptions } from "./fixtures";

// imp-123 (aud-010 A10-01, aud-014 D1): a failed source action shows its cause and error ID next to the control
// that started it, announced once, at 1440 and 375. imp-126 (A10-05): a tap on an unavailable Run now (or on
// imp-081's Import CSV without a template) says why.

const ID = "3f2b8c1e-7d4a-4e9b-9c5f-1a2b3c4d5e6f";
const CAUSE = "The API is restarting. Try again."; // the fixture problem's detail

/** Live regions showing `text`: exactly one means the failure is announced once. */
const announced = (page: Page, text: string) =>
  page.locator('[role="alert"], [role="status"], [aria-live="polite"], [aria-live="assertive"]').filter({ hasText: text, visible: true });

/** Opens Data Health with every PATCH and POST …/run answered by a 503 problem (or `fail`) until `recover()`. */
async function failingWrites(page: Page, options: MockOptions = {}, fail = (route: Route) => route.fulfill({ status: 503, json: problem(503, ID) })) {
  const writes: { method: string; path: string; body: unknown }[] = [];
  let failing = true;
  await mockAdminApi(page, options);
  await page.route(/\/api\/v1\/admin\/sources\/[^/]+(\/run)?$/, (route) => {
    const request = route.request();
    writes.push({ method: request.method(), path: new URL(request.url()).pathname, body: request.postDataJSON() });
    return failing ? fail(route) : route.fallback();
  });
  await page.goto("/admin/data-health");
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
  return { writes, recover: () => (failing = false) };
}

const visible = (scope: Page | Locator, text: string) => scope.getByText(text).filter({ visible: true });
const status = (page: Page) => page.getByRole("region", { name: "Sources", exact: true }).getByRole("status");

for (const [width, height] of [
  [1440, 900],
  [375, 812],
] as const) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height } });

    test("a failed disable keeps its dialog open with the cause and error ID; Disable retries, Cancel and Esc close", async ({ page }) => {
      const { writes, recover } = await failingWrites(page);
      const toggle = page.getByRole("switch", { name: "Google Trends enabled" });
      const dialog = page.getByRole("dialog", { name: "Disable Google Trends?" });
      const submit = dialog.getByRole("button", { name: "Disable", exact: true });
      const alert = dialog.getByRole("alert");
      const failure = `Couldn't disable Google Trends: ${CAUSE}`;

      // 2 clicks: the switch, then Disable.
      await toggle.click();
      await dialog.getByRole("textbox").fill("pausing for review");
      await submit.click();
      await expect(dialog.getByText(failure)).toBeInViewport();
      await expect(dialog.getByText(ID, { exact: true })).toBeInViewport();
      await expect(dialog.getByRole("button", { name: "Copy error ID" })).toBeInViewport();
      await expect(alert).toHaveText(failure);
      await expect(announced(page, CAUSE)).toHaveCount(1);
      await expect(submit).toBeFocused(); // focus never leaves the dialog
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);

      // 1 click retries with the same reason; a second failure is a new alert (announced again), still one.
      const first = await alert.elementHandle();
      await submit.click();
      await expect.poll(() => writes.length).toBe(2);
      await expect.poll(() => first!.evaluate((el) => el.isConnected)).toBe(false);
      await expect(alert).toHaveText(failure);
      await expect(announced(page, CAUSE)).toHaveCount(1);
      expect(writes[1]).toEqual(writes[0]);

      // Cancel closes and takes the error with it: nothing stale behind the dialog or in the next one.
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(dialog).toBeHidden();
      await expect(toggle).toBeFocused();
      await expect(visible(page, CAUSE)).toHaveCount(0);
      await toggle.click();
      await expect(dialog).toBeVisible();
      await expect(visible(dialog, CAUSE)).toHaveCount(0);

      // Esc closes a failed dialog too.
      await submit.click();
      await expect(alert).toHaveText(failure);
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(visible(page, CAUSE)).toHaveCount(0);

      // Once the API answers, one Disable closes the dialog.
      recover();
      await toggle.click();
      await submit.click();
      await expect(dialog).toBeHidden();
      await expect(status(page)).toHaveText("Google Trends disabled.");
      expect(writes).toHaveLength(4);
    });

    test("a failed Run now shows its cause and error ID next to it, announced once", async ({ page }) => {
      const { writes, recover } = await failingWrites(page, { host: { live_runs_allowed: true } });
      const run = page.getByRole("button", { name: "Run CJ Dropshipping now" });
      const failure = `Couldn't start CJ Dropshipping: ${CAUSE}`;

      await run.click(); // 1 click
      expect(writes).toEqual([{ method: "POST", path: "/api/v1/admin/sources/cj/run", body: null }]);
      await expect(visible(page, failure)).toBeInViewport();
      await expect(visible(page, ID)).toBeInViewport();
      await expect(announced(page, CAUSE)).toHaveCount(1);
      await expect(run).toBeFocused();
      if (width === 1440) {
        // Unchanged at 1440: the Sources panel's status line, in view above the table.
        await expect(status(page)).toHaveText(`${failure} (error ID ${ID})`);
      } else {
        // The phone card that holds the button, right under it, with Copy error ID.
        const card = page.getByRole("listitem").filter({ has: run });
        await expect(card.getByRole("alert")).toHaveText(failure);
        await expect(card.getByRole("button", { name: "Copy error ID" })).toBeInViewport();
        const [button, cause] = [(await run.boundingBox())!, (await card.getByRole("alert").boundingBox())!];
        expect(cause.y - (button.y + button.height)).toBeGreaterThanOrEqual(0);
        expect(cause.y - (button.y + button.height)).toBeLessThan(32);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      }

      // A run that starts replaces the failure.
      recover();
      await run.click();
      await expect(status(page)).toHaveText("Run #500 queued for CJ Dropshipping.");
      await expect(visible(page, CAUSE)).toHaveCount(0);
    });

    test("a failed enable without a dialog shows its cause next to the switch (aud-014 D1)", async ({ page }) => {
      // Answered after 300 ms, so the switch is pending (disabled) long enough to drop focus if it could.
      await failingWrites(page, {}, async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 300));
        await route.fulfill({ status: 503, json: problem(503, ID) });
      });
      const toggle = page.getByRole("switch", { name: "Frankfurter FX enabled" });
      const failure = `Couldn't enable Frankfurter FX: ${CAUSE}`;

      await toggle.focus();
      await page.keyboard.press("Space"); // 1 action
      await expect(visible(page, failure)).toBeInViewport();
      await expect(toggle).toBeFocused();
      await expect(visible(page, ID)).toBeInViewport();
      await expect(announced(page, CAUSE)).toHaveCount(1);
      if (width === 375) await expect(page.getByRole("listitem").filter({ has: toggle }).getByRole("alert")).toHaveText(failure);
    });
  });
}

test.describe("375px transport error", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("a Run now the API never answers names the PC next step and has no error ID", async ({ page }) => {
    await failingWrites(page, { host: { live_runs_allowed: true } }, (route) => route.abort("connectionrefused"));
    const run = page.getByRole("button", { name: "Run CJ Dropshipping now" });
    await run.click();
    const card = page.getByRole("listitem").filter({ has: run });
    await expect(card.getByRole("alert")).toHaveText("Couldn't start CJ Dropshipping: the API didn't answer. When it runs on your PC, check that the PC is on.");
    await expect(card.getByRole("alert")).toBeInViewport();
    await expect(card.getByText("Error ID")).toHaveCount(0);
    await expect(card.getByRole("button", { name: "Copy error ID" })).toHaveCount(0);
  });
});

test.describe("375px touch", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  const noTemplate = sources.map((s) => (s.key === "google_trends" ? { ...s, csv_import: null } : s));
  for (const [name, options, reason] of [
    ["Run CJ Dropshipping now", { host: {} }, "Live collectors run only on the collector host."],
    ["Run Frankfurter FX now", { host: { live_runs_allowed: true } }, "Enable the source before running it."],
    ["Import CSV for Google Trends", { sources: noTemplate }, "No CSV template for Google Trends yet."],
  ] as const) {
    test(`a tap on an unavailable control shows why, beside it, and sends nothing: ${name} (imp-126)`, async ({ page }) => {
      const calls = await mockAdminApi(page, options);
      await page.goto("/admin/data-health");
      const control = page.getByRole("button", { name });
      const hint = page.getByRole("tooltip");
      await expect(control).toHaveAttribute("aria-disabled", "true");

      await control.tap({ force: true }); // 1 tap; force: aria-disabled, so Playwright would wait for it to enable
      await expect(hint).toHaveText(reason);
      // Still open after the tap's click: a plain tooltip opens on the tap's focus, then closes on its click, and
      // its fade-out alone would pass the text check above.
      await expect(control).toHaveAttribute("data-state", /-open$/);
      const [button, box] = [(await control.boundingBox())!, (await page.locator("[data-radix-popper-content-wrapper]").boundingBox())!];
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(Math.min(Math.abs(box.y + box.height - button.y), Math.abs(box.y - (button.y + button.height)))).toBeLessThan(16);
      await control.tap({ force: true });
      await expect(hint).toBeHidden();
      expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
    });
  }
});

test("desktop: hover and keyboard focus still show why Run now is unavailable, and a click sends nothing", async ({ page }) => {
  const calls = await mockAdminApi(page);
  await page.goto("/admin/data-health");
  const run = page.getByRole("region", { name: "Sources table" }).getByRole("button", { name: "Run CJ Dropshipping now" });
  const hint = page.getByRole("tooltip");
  await run.hover();
  await expect(hint).toHaveText("Live collectors run only on the collector host.");
  await page.mouse.move(0, 0, { steps: 5 });
  await expect(hint).toBeHidden();
  await run.focus();
  await expect(hint).toHaveText("Live collectors run only on the collector host.");
  await run.click({ force: true }); // aria-disabled: Playwright would wait for it to enable
  expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
});
