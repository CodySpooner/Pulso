import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// A11Y-02 (imp-026, vault Design/Accessibility): under a coarse pointer every visible control owns a 44×44px
// square around its centre. elementFromPoint probes measure the real hit area, so an invisible ::after hit
// area counts, and a neighbour or a clipping ancestor that takes part of the square fails the check.
const routes: { path: string; h1: string; ready?: string }[] = [
  { path: "/", h1: "Daily Pulse" },
  { path: "/admin/ui", h1: "UI gallery" },
  { path: "/admin/data-health", h1: "Data Health", ready: "As of Oct 22, 14:00 UTC" },
];

function measure({ min, root }: { min: number; root: string }) {
  const controls =
    "a[href], button, input, select, textarea, summary, [role=button], [role=link], [role=tab], [role=switch], [role=checkbox], [role=radio], [role=menuitem], [role=option], [tabindex]:not([tabindex='-1'])";
  const half = min / 2 - 1; // 1px inside the edge: Chrome rounds hit-test points to whole pixels
  const offsets = [-half, 0, half];
  const small: string[] = [];
  let checked = 0;
  let visuallySmall = 0;
  for (const el of document.querySelector(root)!.querySelectorAll<HTMLElement>(controls)) {
    if (el.matches(":disabled, [aria-disabled=true]") || !el.checkVisibility({ visibilityProperty: true, opacityProperty: true })) continue;
    el.scrollIntoView({ block: "center", inline: "center" });
    const r = el.getBoundingClientRect();
    const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2];
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue; // off screen: the unfocused skip link
    checked++;
    if (r.width < min || r.height < min) visuallySmall++;
    const missed = offsets.some((dx) => offsets.some((dy) => !el.contains(document.elementFromPoint(cx + dx, cy + dy))));
    const name = el.getAttribute("aria-label") || el.textContent?.trim().slice(0, 40) || el.tagName;
    if (missed) small.push(`${name} (${Math.round(r.width)}×${Math.round(r.height)})`);
  }
  const pageScroll = document.documentElement.scrollWidth - innerWidth; // a hit area at a screen edge must not widen the page
  return { coarse: matchMedia("(pointer: coarse)").matches, checked, visuallySmall, small, pageScroll };
}

for (const width of [375, 1024, 1440]) {
  test.describe(`touch ${width}px`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch: true });

    for (const { path, h1, ready } of routes) {
      test(`every control on ${path} has a 44×44px hit area`, async ({ page }) => {
        await mockAdminApi(page); // Data Health and the nav badge render from the DH-1 fixtures
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1, name: h1 })).toBeVisible();
        if (ready) await expect(page.getByText(ready)).toBeVisible();
        const result = await page.evaluate(measure, { min: 44, root: "body" });
        console.log(`${width}px ${path}: ${result.checked} controls, ${result.visuallySmall} drawn under 44px, ${result.small.length} hit areas under 44px`);
        expect(result.coarse).toBe(true);
        expect(result.checked).toBeGreaterThan(0);
        expect(result.small).toEqual([]);
        expect(result.pageScroll).toBe(0);
      });
    }
  });
}

// The shared dialogs: the phone's More sheet, the command palette (Search tab), and Data Health's run drawer
// (right sheet) and disable-reason dialog.
const dialogs: { name: string; path: string; open: (page: Page) => Promise<void> }[] = [
  { name: "More sheet", path: "/", open: (page) => page.getByRole("navigation", { name: "Tab bar" }).getByRole("button", { name: "More" }).click() },
  { name: "command palette", path: "/", open: (page) => page.getByRole("navigation", { name: "Tab bar" }).getByRole("button", { name: "Search" }).click() },
  { name: "run drawer", path: "/admin/data-health", open: (page) => page.getByRole("button", { name: "Shopify stores: open runs" }).click() },
  { name: "reason dialog", path: "/admin/data-health", open: (page) => page.getByRole("switch", { name: "CJ Dropshipping enabled" }).click() },
];

test.describe("touch 375px dialogs", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  for (const { name, path, open } of dialogs) {
    test(`every control in the ${name} has a 44×44px hit area`, async ({ page }) => {
      await mockAdminApi(page);
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await open(page);
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.waitForTimeout(400); // the enter animation moves the dialog
      const result = await page.evaluate(measure, { min: 44, root: "[role=dialog]" });
      console.log(`375px ${name}: ${result.checked} controls, ${result.visuallySmall} drawn under 44px, ${result.small.length} hit areas under 44px`);
      expect(result.checked).toBeGreaterThan(0);
      expect(result.small).toEqual([]);
    });
  }
});

// imp-045 (vault Design/Tables & Data Density): every table density draws 44px rows under a coarse pointer, and
// a fine pointer keeps the dense 28 / 32 / 40px. Data Health renders all three: open gaps (compact), planned
// sources (default) and sources (comfortable); a bare probe per utility reads the token without cell content.
const rowTouch = [
  { pointer: "coarse", hasTouch: true, width: 1024, heights: { "row-h-compact": 44, "row-h": 44, "row-h-comfortable": 44 } },
  { pointer: "fine", hasTouch: false, width: 1440, heights: { "row-h-compact": 28, "row-h": 32, "row-h-comfortable": 40 } },
];

for (const { pointer, hasTouch, width, heights } of rowTouch) {
  test.describe(`table rows ${pointer} pointer`, () => {
    test.use({ viewport: { width, height: 900 }, hasTouch });

    test(`every density draws its ${pointer}-pointer row height`, async ({ page }) => {
      await mockAdminApi(page);
      await page.goto("/admin/data-health");
      await expect(page.getByText("As of Oct 22, 14:00 UTC")).toBeVisible();
      await expect(page.getByRole("region", { name: "Open gaps" })).toBeVisible();
      const result = await page.evaluate((classes) => {
        const probe = (cls: string) => {
          const el = document.body.appendChild(document.createElement("div"));
          el.className = cls;
          const h = el.getBoundingClientRect().height;
          el.remove();
          return h;
        };
        const rows = (cls: string) =>
          [...document.querySelectorAll(`tr.${cls}`)].filter((tr) => tr.checkVisibility()).map((tr) => tr.getBoundingClientRect().height);
        return {
          coarse: matchMedia("(pointer: coarse)").matches,
          probes: Object.fromEntries(classes.map((c) => [c, probe(c)])),
          rows: Object.fromEntries(classes.map((c) => [c, rows(c)])),
          pageScroll: document.documentElement.scrollWidth - innerWidth,
        };
      }, Object.keys(heights));
      console.log(`${pointer} ${width}px rows: ${JSON.stringify(result.probes)} ${JSON.stringify(result.rows)}`);
      expect(result.coarse).toBe(hasTouch);
      expect(result.probes).toEqual(heights);
      for (const [cls, min] of Object.entries(heights)) {
        expect(result.rows[cls].length, `${cls} rows rendered`).toBeGreaterThan(0);
        for (const h of result.rows[cls]) expect(h, cls).toBeGreaterThanOrEqual(min);
      }
      expect(result.pageScroll).toBe(0);
    });
  });
}
