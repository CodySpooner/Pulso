import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi } from "./fixtures";

// imp-092: while an import runs, Choose another… and a dropped file can't replace its file. Both went through
// check(), which reset the running commit: the server still imported, but its outcome and Open runs were lost
// and the new file was checked instead.
const file = { name: "rates.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-01,USD,JPY,150\n") };
const other = { name: "other.csv", mimeType: "text/csv", buffer: Buffer.from("date,base,quote,rate\n2026-01-02,USD,EUR,0.9\n") };
const COMMIT = /\/api\/v1\/admin\/sources\/[^/]+\/import$/;

/** Holds the commit until `release()`; `fail` then answers it with a 503 instead of the fixture run. */
async function holdCommit(page: Page, fail = false) {
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(COMMIT, async (route) => {
    await held;
    if (!fail) return route.fallback();
    await route.fulfill({
      status: 503,
      json: { type: "about:blank", title: "Service Unavailable", status: 503, code: "unavailable", detail: "The API is restarting. Try again in a minute.", request_id: "e2e-503", errors: [] },
    });
  });
  return release;
}

/** Drags `f` over the drop zone and drops it, as a file dragged in from the desktop. */
async function drop(zone: Locator, f: typeof other) {
  const dataTransfer = await zone.page().evaluateHandle(({ name, text }) => {
    const dt = new DataTransfer();
    dt.items.add(new File([text], name, { type: "text/csv" }));
    return dt;
  }, { name: f.name, text: f.buffer.toString() });
  await zone.dispatchEvent("dragover", { dataTransfer });
  await zone.dispatchEvent("drop", { dataTransfer });
}

async function startImport(page: Page) {
  await page.goto("/admin/data-health");
  const panel = page.getByRole("region", { name: "CSV import" });
  const input = panel.locator('input[type="file"]');
  await input.setInputFiles(file);
  await panel.getByRole("button", { name: "Import 3 rows" }).click();
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
  return { panel, input, zone: input.locator(".."), choose: panel.getByRole("button", { name: "Choose another…" }) };
}

const previews = (calls: { path: string }[]) => calls.filter((c) => c.path.endsWith("/import/preview"));
const commits = (calls: { method: string; path: string }[]) => calls.filter((c) => c.method === "POST" && c.path.endsWith("/import"));

test("a running import keeps its file against Choose another… and a drop, then replacing works again", async ({ page }) => {
  const calls = await mockAdminApi(page);
  const release = await holdCommit(page);
  let choosers = 0;
  page.on("filechooser", () => choosers++);
  const { panel, input, zone, choose } = await startImport(page);

  // Keyboard and pointer: Choose another… says it is unavailable, keeps a full-strength ring and opens no picker.
  await expect(choose).toHaveAttribute("aria-disabled", "true");
  await choose.focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Space");
  await choose.click({ force: true });
  await expect(choose).toBeFocused();
  expect(await choose.evaluate((el) => getComputedStyle(el).outlineStyle)).not.toBe("none");
  expect(await choose.evaluate((el) => getComputedStyle(el).opacity)).toBe("1"); // opacity would fade the ring below 3:1
  // A file that reaches the input anyway, and a drop, both leave the running import alone.
  await input.setInputFiles(other);
  await drop(zone, other);
  await expect(zone).not.toHaveClass(/border-brand/); // the zone doesn't invite a drop it would ignore
  await expect(panel.getByRole("status")).toHaveText("Importing rates.csv…");
  await expect(zone).toContainText("rates.csv");

  // The original import finishes: its outcome and Open runs belong to it, and nothing else was sent.
  release();
  await expect(panel.getByRole("status")).toHaveText(/^Imported into Frankfurter FX as run #501: 3 new/);
  expect(choosers).toBe(0);
  expect(previews(calls)).toHaveLength(1);
  expect(commits(calls)).toHaveLength(1);
  await panel.getByRole("button", { name: "Open runs" }).click();
  await expect(page.getByRole("dialog", { name: "Frankfurter FX" })).toBeVisible();
  await page.keyboard.press("Escape");

  // Done: a drop checks a new file as before.
  await expect(panel.getByRole("button", { name: "Choose CSV…" })).not.toHaveAttribute("aria-disabled", "true");
  await drop(zone, other);
  await expect(panel.getByRole("status")).toHaveText("3 valid rows · 1 invalid row");
  await expect(zone).toContainText("other.csv");
  expect(previews(calls)).toHaveLength(2);
});

test("after a failed import, Choose another… replaces the file as before", async ({ page }) => {
  const calls = await mockAdminApi(page);
  const release = await holdCommit(page, true);
  const { panel, zone, choose } = await startImport(page);
  release();
  await expect(panel.getByRole("alert")).toHaveText(/^The API is restarting/);

  await expect(choose).not.toHaveAttribute("aria-disabled", "true");
  await choose.focus();
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles(other);
  await expect(panel.getByRole("status")).toHaveText("3 valid rows · 1 invalid row");
  await expect(panel.getByRole("alert")).toHaveText("");
  await expect(zone).toContainText("other.csv");
  expect(previews(calls)).toHaveLength(2);
});
