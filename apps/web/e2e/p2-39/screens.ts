import { expect, type Page } from "@playwright/test";

import { mockPopularApi } from "../google-popular/fixtures";
import { mockMatchingApi, title } from "../matching/fixtures";
import { mockFeedApi, mockProductApi, PRODUCT_ID } from "../products/fixtures";
import { mockProfitApi } from "../products/profit-fixtures";
import { mockSellersApi } from "../products/sellers-fixtures";
import { mockSuppliersApi } from "../products/suppliers-fixtures";
import { mockSearchApi, openPalette } from "../search/fixtures";
import { mockSettingsApi } from "../settings/fixtures";

// p2-39 (Phase 2 end): every Phase 2 screen in its loaded state, from the existing fixtures (the E2E auth bypass,
// never a database restore). phase-end.spec.ts runs the AGENTS.md §8 checks that a browser can measure on each.

export interface Screen {
  name: string;
  /** Mocks, then navigation; leaves the screen loaded. */
  open: (page: Page) => Promise<unknown>;
  /** Where its keyboard stops live: the page's main, or the palette dialog. */
  scope: string;
}

const PRODUCT = `/products/${PRODUCT_ID}`;
const settled = (page: Page) => expect(page.locator(".bg-skeleton:visible")).toHaveCount(0);

export const SCREENS: Screen[] = [
  {
    name: "discover-table",
    scope: "main",
    open: async (page) => {
      await mockFeedApi(page);
      await page.goto("/discover?view=table");
      await expect(page.getByRole("region", { name: "Products" }).getByRole("row").nth(1)).toBeVisible();
    },
  },
  {
    name: "discover-grid",
    scope: "main",
    open: async (page) => {
      await mockFeedApi(page);
      await page.goto("/discover?view=grid");
      await expect(page.getByRole("list", { name: "Products" }).getByRole("article").first()).toBeVisible();
    },
  },
  {
    name: "product-overview",
    scope: "main",
    open: async (page) => {
      await mockProductApi(page);
      await page.goto(PRODUCT);
      await expect(page.getByRole("region", { name: "Notes" })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "product-trends",
    scope: "main",
    open: async (page) => {
      await mockProductApi(page);
      await page.goto(`${PRODUCT}?tab=trends`);
      await expect(page.getByText("Collection gap · 3 days, no data").first()).toBeAttached();
      await settled(page);
    },
  },
  {
    name: "product-suppliers",
    scope: "main",
    open: async (page) => {
      await mockSuppliersApi(page);
      await page.goto(`${PRODUCT}?tab=suppliers`);
      await expect(page.getByRole("region", { name: "Best margin", exact: true })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "product-sellers",
    scope: "main",
    open: async (page) => {
      await mockSellersApi(page);
      await page.goto(`${PRODUCT}?tab=sellers`);
      await expect(page.getByRole("region", { name: "Price spread" })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "product-profit",
    scope: "main",
    open: async (page) => {
      await mockProfitApi(page);
      await page.goto(`${PRODUCT}?tab=profit`);
      await expect(page.getByRole("region", { name: "Scenario" })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "matching",
    scope: "main",
    open: async (page) => {
      await mockMatchingApi(page);
      await page.goto("/admin/matching");
      await expect(page.getByRole("article", { name: `Listing A: ${title(0, "a")}` })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "settings",
    scope: "main",
    open: async (page) => {
      await mockSettingsApi(page);
      await page.goto("/settings");
      await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "google-popular",
    scope: "main",
    open: async (page) => {
      await mockPopularApi(page);
      await page.goto("/google-popular");
      await expect(page.getByRole("main").getByRole("row").nth(1)).toBeVisible();
      await settled(page);
    },
  },
  {
    name: "palette-search",
    scope: "[role=dialog]",
    open: async (page) => {
      await mockSearchApi(page);
      const input = await openPalette(page);
      await input.pressSequentially("glow", { delay: 20 });
      await expect(page.getByRole("option", { name: /^Shenzhen Glowtech Co\./ })).toBeVisible();
    },
  },
];

export interface FocusStop {
  what: string;
  ring: boolean;
  visible: boolean;
}

/** The focused element: does it show a ring (the global :focus-visible outline, or a box-shadow in the ring colour)? */
export function focusStop(scope: string): FocusStop | null {
  const el = document.activeElement as HTMLElement | null;
  if (!el || el === document.body || !el.closest(scope)) return null;
  const ringColour = getComputedStyle(el).getPropertyValue("--ring").trim();
  const probe = document.createElement("i");
  probe.style.color = ringColour;
  document.body.append(probe);
  const ringRgb = getComputedStyle(probe).color;
  probe.remove();
  // A stretched link or a bare input draws its ring on the card or field around it (`has-[a:focus-visible]:outline-2`);
  // only the width is read there, since `transition-colors` may still be fading the outline's colour in.
  const ringed = (e: Element) => {
    const c = getComputedStyle(e);
    return (c.outlineStyle !== "none" && parseFloat(c.outlineWidth) > 0) || c.boxShadow.includes(ringRgb);
  };
  const shown = (e: Element) => {
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  // The ring has to be painted where the eye can see it: an sr-only radio's own outline doesn't count, its label's does.
  let host: Element | null = ringed(el) && shown(el) ? el : null;
  for (let a = el.parentElement, i = 0; a && i < 5 && !host; a = a.parentElement, i++) if (ringed(a) && shown(a)) host = a;
  return {
    what: `${el.tagName.toLowerCase()}${el.getAttribute("role") ? `[role=${el.getAttribute("role")}]` : ""} "${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 48)}"`,
    ring: host !== null,
    visible: shown(el) || host !== null,
  };
}

export interface ContrastMiss {
  text: string;
  ratio: number;
  needs: number;
  fg: string;
  bg: string;
}

/** WCAG 2 contrast of every visible text run in `scope` against the backgrounds it is painted on (DOM ancestry,
 *  alpha composited; colours read back through a canvas so oklch()/color-mix() resolve like the browser does).
 *  Text over an image or gradient, and disabled controls (WCAG-exempt), are skipped. */
export function contrastMisses(scope: string): ContrastMiss[] {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  const rgba = (css: string): number[] => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = "#000";
    ctx.fillStyle = css;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const over = (top: number[], under: number[]) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
  const lum = (c: number[]) =>
    [0, 1, 2]
      .map((i) => c[i] / 255)
      .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
      .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  const hex = (c: number[]) => `#${c.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
  const root = rgba(getComputedStyle(document.body).backgroundColor);

  const misses: ContrastMiss[] = [];
  const seen = new Set<Element>();
  const walker = document.createTreeWalker(document.querySelector(scope) ?? document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    if (!el || seen.has(el) || !node.textContent?.trim()) continue;
    seen.add(el);
    if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
    if (el.closest("svg, canvas, :disabled, [aria-disabled=true], [inert]")) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const box = range.getBoundingClientRect();
    const clip = el.getBoundingClientRect(); // sr-only: a 1px box that its nowrap text overflows (p3-12)
    if (box.width < 2 || box.height < 2 || clip.width < 2 || clip.height < 2) continue;

    let fg = rgba(getComputedStyle(el).color);
    const layers: number[][] = [];
    let image = false;
    for (let a: Element | null = el; a; a = a.parentElement) {
      const s = getComputedStyle(a);
      fg = [...fg.slice(0, 3), fg[3] * parseFloat(s.opacity)];
      if (s.backgroundImage !== "none") image = true;
      const bg = rgba(s.backgroundColor);
      if (bg[3] > 0) layers.push(bg);
      if (bg[3] >= 1) break;
    }
    if (image) continue;
    const bg = layers.reverse().reduce((under, top) => over(top, under), root);
    const text = over(fg, bg);
    const [l1, l2] = [lum(text), lum(bg)].sort((x, y) => y - x);
    const ratio = (l1 + 0.05) / (l2 + 0.05);
    const s = getComputedStyle(el);
    const size = parseFloat(s.fontSize);
    const large = size >= 24 || (size >= 18.66 && Number(s.fontWeight) >= 700);
    const needs = large ? 3 : 4.5;
    if (ratio < needs - 0.005)
      misses.push({ text: node.textContent.trim().slice(0, 48), ratio: Math.round(ratio * 100) / 100, needs, fg: hex(text), bg: hex(bg) });
  }
  return misses;
}
