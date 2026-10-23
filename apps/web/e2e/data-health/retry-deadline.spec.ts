import { expect, test, type Locator, type Page } from "@playwright/test";

import { mockAdminApi, NOW, sources, suppressedSources } from "./fixtures";

// imp-094 (aud-010 A10-03, aud-011 B11-06): a blocked source's retry deadline stays readable in its row and
// card, the re-enable dialog states a future deadline instead of implying it has passed, and the source type
// and status notes are at least 12px. Fixtures: now 14:00 UTC, Shopify retry_not_before 15:00 UTC.

const PAGE = "/admin/data-health";
const DEADLINE = "Oct 22, 15:00 UTC";

async function open(page: Page) {
  await page.goto(PAGE);
  await expect(page.getByRole("heading", { level: 1, name: "Data Health" })).toBeVisible();
}

/** Shopify with its retry deadline `hoursAgo` before NOW (null: no deadline). */
function shopifyRetry(hoursAgo: number | null) {
  const at = hoursAgo == null ? null : new Date(NOW.getTime() - hoursAgo * 3_600_000).toISOString();
  return sources.map((s) => (s.key === "shopify_stores" ? { ...s, retry_not_before: at } : s));
}

/** Whether every character of `text` inside `container` is painted, not cut by an ellipsis, a clipping box or the viewport. */
function fullyShown(container: Locator, text: string) {
  return container.evaluate((root, text) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
      const start = node.data.indexOf(text);
      if (start < 0) continue;
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, start + text.length);
      const r = range.getBoundingClientRect();
      if (r.left < 0 || r.right > window.innerWidth) return false;
      for (let el = node.parentElement; el; el = el.parentElement) {
        if (getComputedStyle(el).overflowX === "visible") continue;
        const box = el.getBoundingClientRect();
        if (r.left < box.left - 0.5 || r.right > box.right + 0.5) return false;
      }
      return true;
    }
    return false;
  }, text);
}

/** The computed font size, in px, of the element that directly holds `text`. */
async function fontSize(container: Locator, text: string | RegExp) {
  return container.getByText(text, { exact: typeof text === "string" }).first().evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
}

const typeLabels = [
  ["Shopify stores", "Public endpoint"],
  ["CJ Dropshipping", "Official API"],
  ["Google Trends", "Vendor API"],
  ["Frankfurter FX", "Official API"],
] as const;

test("1440: the blocked row shows its full retry deadline; type and status text are at least 12px", async ({ page }) => {
  await mockAdminApi(page, { sources: suppressedSources }); // CJ carries a skip note too
  await open(page);
  const table = page.getByRole("region", { name: "Sources table" });
  const shopify = table.getByRole("row", { name: /Shopify stores/ });
  await expect(shopify).toContainText(DEADLINE);
  expect(await fullyShown(shopify, DEADLINE)).toBe(true);

  for (const [name, type] of typeLabels) expect(await fontSize(table.getByRole("row", { name: new RegExp(name) }), type)).toBeGreaterThanOrEqual(12);
  expect(await fontSize(shopify, "5 consecutive 429 responses")).toBeGreaterThanOrEqual(12);
  expect(await fontSize(shopify, new RegExp(DEADLINE))).toBeGreaterThanOrEqual(12);
  expect(await fontSize(table.getByRole("row", { name: /CJ Dropshipping/ }), /Run #419 was still active/)).toBeGreaterThanOrEqual(12);
});

test.describe("phone width", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("375: the blocked card shows its full retry deadline at 12px with no horizontal scroll", async ({ page }) => {
    await mockAdminApi(page);
    await open(page);
    const card = page.getByRole("listitem").filter({ has: page.getByRole("button", { name: "Shopify stores: open runs" }) });
    await expect(card).toContainText(DEADLINE);
    expect(await fullyShown(card, DEADLINE)).toBe(true);
    expect(await fontSize(card, "Public endpoint")).toBeGreaterThanOrEqual(12);
    expect(await fontSize(card, new RegExp(DEADLINE))).toBeGreaterThanOrEqual(12);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  });
});

test("re-enable before the deadline: the dialog states it once and that earlier runs are deferred; the PATCH is unchanged", async ({ page }) => {
  const calls = await mockAdminApi(page);
  await open(page);
  const toggle = page.getByRole("region", { name: "Sources table" }).getByRole("switch", { name: "Shopify stores enabled" });
  await toggle.focus();
  await page.keyboard.press("Space");
  const dialog = page.getByRole("dialog", { name: "Re-enable Shopify stores?" });
  await expect(dialog).toHaveAccessibleDescription(new RegExp(`${DEADLINE} \\(in 1h\\)\\. You can re-enable now, but runs before then are deferred\\.`));
  expect((await dialog.innerText()).split(DEADLINE)).toHaveLength(2); // stated exactly once
  await expect(dialog).not.toContainText(/passed|elapsed/i);
  await expect(dialog.getByRole("textbox")).not.toHaveAttribute("placeholder", /passed|elapsed/i);

  await page.keyboard.type("store reachable again");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Re-enable" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(toggle).toBeFocused();
  expect(calls.filter((c) => c.method !== "GET")).toEqual([{ method: "PATCH", path: "/v1/admin/sources/shopify_stores", body: { enabled: true, reason: "store reachable again" } }]);
});

for (const [when, hoursAgo] of [
  ["after a passed deadline", 1],
  ["with no deadline", null],
] as const) {
  test(`re-enable ${when}: the dialog reads as before, with no deferral`, async ({ page }) => {
    await mockAdminApi(page, { sources: shopifyRetry(hoursAgo) });
    await open(page);
    await page.getByRole("region", { name: "Sources table" }).getByRole("switch", { name: "Shopify stores enabled" }).click();
    const dialog = page.getByRole("dialog", { name: "Re-enable Shopify stores?" });
    await expect(dialog).toHaveAccessibleDescription(
      "The block rule turned this source off. Say why it is safe to try again; the reason goes to the source's audit log (§4.2).",
    );
    await expect(dialog).not.toContainText(/deferred|UTC/);
    await expect(dialog.getByRole("textbox")).toHaveAttribute("placeholder", "For example: retry-after passed, store reachable again");
  });
}
