import { expect, test } from "@playwright/test";

// A11Y-02 (imp-026, vault Design/Accessibility): under a coarse pointer every visible control owns a 44×44px
// square around its centre. elementFromPoint probes measure the real hit area, so an invisible ::after hit
// area counts, and a neighbour or a clipping ancestor that takes part of the square fails the check.
const routes = [
  { path: "/", h1: "Daily Pulse" },
  { path: "/admin/ui", h1: "UI gallery" },
  { path: "/admin/data-health", h1: "Data Health" },
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

    for (const { path, h1 } of routes) {
      test(`every control on ${path} has a 44×44px hit area`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1, name: h1 })).toBeVisible();
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

// The shared dialogs: the phone's More sheet and the command palette (Search tab).
test.describe("touch 375px dialogs", () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true });

  for (const opener of ["More", "Search"]) {
    test(`every control in the ${opener} dialog has a 44×44px hit area`, async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();
      await page.getByRole("navigation", { name: "Tab bar" }).getByRole("button", { name: opener }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.waitForTimeout(400); // the enter animation moves the dialog
      const result = await page.evaluate(measure, { min: 44, root: "[role=dialog]" });
      console.log(`375px ${opener} dialog: ${result.checked} controls, ${result.visuallySmall} drawn under 44px, ${result.small.length} hit areas under 44px`);
      expect(result.checked).toBeGreaterThan(0);
      expect(result.small).toEqual([]);
    });
  }
});
