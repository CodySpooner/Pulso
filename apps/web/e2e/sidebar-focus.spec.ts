import { expect, test, type Page } from "@playwright/test";

import { mockAdminApi } from "./data-health/fixtures";

// imp-083 (aud-011 B11-02): the sidebar nav scrolls inside a box whose bottom 48px fade out
// (`mask-b-from-[calc(100%-3rem)]` in shell/sidebar.tsx). Tabbing through every nav link, the focused link's
// whole ring (outline + offset) must sit inside the box and above the fade: never clipped, never faded.
const FADE = 48;
const NAV_LINKS = 20; // every link in lib/nav.ts navGroups

function ringFit(fade: number) {
  const el = document.activeElement as HTMLElement;
  const box = el.closest("aside nav")?.parentElement;
  if (!box) return null;
  const s = getComputedStyle(el);
  const ring = parseFloat(s.outlineWidth) + parseFloat(s.outlineOffset);
  const r = el.getBoundingClientRect();
  const b = box.getBoundingClientRect();
  return {
    href: el.getAttribute("href"),
    outline: s.outlineStyle,
    clippedTop: Math.max(0, b.top - (r.top - ring)), // px of ring above the box's clip edge
    inFade: Math.max(0, r.bottom + ring - (b.bottom - fade)), // px of ring inside the bottom fade
    overflows: box.scrollHeight > box.clientHeight,
  };
}

async function walk(page: Page, key: "Tab" | "Shift+Tab") {
  const stops = [];
  for (let i = 0; i < NAV_LINKS; i++) {
    if (i > 0) await page.keyboard.press(key);
    const fit = await page.evaluate(ringFit, FADE);
    expect(fit, `${key} stop ${i} left the sidebar nav`).not.toBeNull();
    stops.push(fit!);
  }
  return stops;
}

const sizes = [
  { width: 1440, height: 900 }, // the audit's viewport
  { width: 1440, height: 700 }, // a short window: the list scrolls further
  { width: 1024, height: 700 }, // the 56px icon rail uses the same scroll box
];

for (const viewport of sizes) {
  for (const theme of ["dark", "light"] as const) {
    test(`sidebar focus rings stay whole at ${viewport.width}×${viewport.height} (${theme})`, async ({ page }) => {
      await mockAdminApi(page); // the Data Health nav badge renders from the DH-1 fixtures
      await page.setViewportSize(viewport);
      await page.addInitScript((t) => localStorage.setItem("theme", t), theme);
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1, name: "Daily Pulse" })).toBeVisible();

      // From the top of the page: the skip link, the logo, then the first nav link.
      const first = page.locator("aside nav").getByRole("link").first();
      for (let i = 0; i < 4 && !(await first.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
      await expect(first).toBeFocused();

      const down = await walk(page, "Tab");
      const up = await walk(page, "Shift+Tab");
      const bad = [...down, ...up].filter((s) => s.outline !== "solid" || s.clippedTop > 0.5 || s.inFade > 0.5);
      console.log(`${viewport.width}×${viewport.height} ${theme}: ${down.length + up.length} stops, ${bad.length} clipped or faded`);

      expect(down[0].href).toBe("/");
      expect(down.at(-1)!.href).toBe("/admin/ui");
      expect(up.at(-1)!.href).toBe("/");
      if (viewport.height === 700) expect(down[0].overflows).toBe(true); // the walk really scrolls the box
      expect(bad).toEqual([]);
    });
  }
}
