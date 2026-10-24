import { expect, test } from "@playwright/test";

import { mockAdminApi, sources } from "./fixtures";

// imp-098 (aud-011 B11-03/B11-04): every run-drawer fact reads in full on a phone (touch has no hover),
// and its counts are grouped like the Sources table's.

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 375]) {
    test(`drawer facts wrap and group counts at ${width}px ${theme}`, async ({ page }) => {
      await mockAdminApi(page);
      await page.setViewportSize({ width, height: width < 1024 ? 812 : 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/admin/data-health");

      for (const name of ["Shopify stores", "CJ Dropshipping"]) {
        await page.getByRole("button", { name: `${name}: open runs` }).first().click();
        const drawer = page.getByRole("dialog", { name });
        await expect(drawer).toContainText("#9001"); // the newest run is expanded, targets loaded
        const clipped = await drawer.locator("dd").evaluateAll((dds) => dds.filter((dd) => dd.scrollWidth > dd.clientWidth).map((dd) => dd.textContent));
        expect(clipped).toEqual([]);
        const key = drawer.locator("dt", { hasText: /^Key$/ }).locator("+ dd > span");
        await expect(key).toHaveCSS("font-family", /mono/i);
        expect(await key.evaluate((el) => el.getClientRects().length)).toBe(1); // one unbroken line
        expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);

        if (name === "CJ Dropshipping") {
          const fact = (label: string) => drawer.locator("dt", { hasText: new RegExp(`^${label}$`) }).locator("+ dd");
          await expect(fact("Quota")).toHaveText("2,650 / 50,000");
          await expect(fact("Rows")).toHaveText("1,240 fetched · 36 inserted · 112 updated · 1,092 unchanged");
          await expect(fact("Requests")).toHaveText("26 · last code 200");
        }
        await page.keyboard.press("Escape");
        await expect(drawer).toBeHidden();
      }
    });
  }
}

// imp-119/127 (aud-010 A10-06): every source's facts read in the table's and the pill's words, never a raw API value
// (the Key fact keeps its raw key), and the deadline reads "Retry after" like the row and the re-enable dialog.
const RAW = /\b(active|enabled|disabled|blocked|public_endpoint|official_api|vendor|internal)\b/; // labels are capitalised
const wanted: Record<string, { type: string; status: string }> = {
  "Shopify stores": { type: "Public endpoint · Phase 1", status: "Blocked · Disabled since Oct 22, 09:00 UTC" },
  "CJ Dropshipping": { type: "Official API · Phase 1", status: "Healthy · Enabled" },
  "Google Trends": { type: "Vendor API · Phase 1", status: "Overdue · Enabled" },
  "Frankfurter FX": { type: "Official API · Phase 1", status: "Disabled" },
};

test("drawer facts use the table's and the pill's words for every source", async ({ page }) => {
  await mockAdminApi(page);
  await page.goto("/admin/data-health");
  for (const [name, want] of Object.entries(wanted)) {
    await page.getByRole("button", { name: `${name}: open runs` }).first().click();
    const facts = page.getByRole("dialog", { name }).locator("dl").first();
    const fact = (label: string) => facts.locator("dt", { hasText: new RegExp(`^${label}$`) }).locator("+ dd");
    await expect(fact("Type · phase")).toHaveText(want.type);
    await expect(fact("Status")).toHaveText(want.status);
    await expect(fact("Retry after")).toHaveCount(1);
    await expect(facts.getByText("Retry not before")).toHaveCount(0);
    const raw = await facts.locator("dt").evaluateAll(
      (dts, re) => dts.filter((dt) => dt.textContent !== "Key" && new RegExp(re).test(dt.nextElementSibling!.textContent!)).map((dt) => dt.textContent),
      RAW.source,
    );
    expect(raw).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  }
});

// imp-128 (aud-010 A10-07): a never-run source's empty state names only the actions that source has.
test("a never-run source off the collector host names CSV import, not Run now", async ({ page }) => {
  await mockAdminApi(page); // Frankfurter FX: disabled, live runs off here, CSV import ready
  await page.goto("/admin/data-health");
  await page.getByRole("button", { name: "Frankfurter FX: open runs" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Frankfurter FX" });
  await expect(drawer.getByRole("heading", { name: "No runs yet" })).toBeVisible();
  await expect(drawer).toContainText("This source is disabled, so the collector host doesn't run it.");
  await expect(drawer).toContainText("CSV import panel");
  await expect(drawer).not.toContainText("Run now");
});

test("a never-run source that can run names Run now", async ({ page }) => {
  await mockAdminApi(page, {
    host: { live_runs_allowed: true },
    sources: sources.map((s) => (s.key === "fx_frankfurter" ? { ...s, enabled: true, status: "active", csv_import: "preview_only" } : s)),
  });
  await page.goto("/admin/data-health");
  await page.getByRole("button", { name: "Frankfurter FX: open runs" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Frankfurter FX" });
  await expect(drawer.getByRole("heading", { name: "No runs yet" })).toBeVisible();
  await expect(drawer).toContainText("Run now");
  await expect(drawer).not.toContainText("CSV import panel"); // preview only: an import adds no run
});

// imp-131 (aud-011 B11-07): at 375 the targets table shows every column, its header on one line, and stays a
// keyboard-scrollable region.
for (const theme of ["dark", "light"] as const) {
  test(`targets table fits a phone with a one-line header ${theme}`, async ({ page }) => {
    await mockAdminApi(page);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
    await page.goto("/admin/data-health");
    await page.getByRole("button", { name: "Shopify stores: open runs" }).first().click();
    const region = page.getByRole("dialog", { name: "Shopify stores" }).getByRole("region", { name: "Run 412 targets" });
    await expect(region).toContainText("#9001");
    await expect(region).toHaveAttribute("tabindex", "0");
    expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
    const lines = await region.locator("th").evaluateAll((ths) =>
      ths.map((th) => {
        const range = document.createRange();
        range.selectNodeContents(th);
        return range.getClientRects().length;
      }),
    );
    expect(lines).toEqual([1, 1, 1]);
  });
}
