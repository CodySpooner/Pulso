import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

// WCAG 2.x contrast check of the design tokens (vault Design/Color & Tokens, Accessibility): every text
// token clears 4.5:1 on every surface it can sit on, and UI marks (focus ring, brand indicators, input
// outlines) plus large text clear 3:1, in both themes. Translucent tokens are composited over the surface
// they sit on; color-mix() is resolved in OKLab like the browser does.

type RGBA = [number, number, number, number]; // sRGB 0–255, alpha 0–1
type Theme = "dark" | "light";

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function themeVars(theme: Theme): Map<string, string> {
  const vars = new Map<string, string>();
  for (const [, selectors, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const applies = selectors.split(",").some((s) => [":root", `.${theme}`].includes(s.trim()));
    if (!applies) continue;
    for (const [, name, value] of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars.set(name, value.trim());
  }
  return vars;
}

function resolve(value: string, vars: Map<string, string>): string {
  return value.replace(/var\((--[\w-]+)\)/g, (_, name: string) => {
    const next = vars.get(name);
    if (next === undefined) throw new Error(`Unknown token ${name}`);
    return resolve(next, vars);
  });
}

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const fromLinear = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function toOklab([r, g, b]: RGBA): [number, number, number] {
  const [lr, lg, lb] = [r, g, b].map((c) => toLinear(c / 255));
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function fromOklab([L, a, b]: [number, number, number], alpha: number): RGBA {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((c) => Math.min(255, Math.max(0, fromLinear(c) * 255)));
  return [rgb[0], rgb[1], rgb[2], alpha];
}

function parseColor(raw: string): RGBA {
  const value = raw.trim();
  if (value === "transparent") return [0, 0, 0, 0];
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)).concat(1) as RGBA;
  const rgb = value.match(/^rgb\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+))?\s*\)$/);
  if (rgb) return [+rgb[1], +rgb[2], +rgb[3], rgb[4] === undefined ? 1 : +rgb[4]];
  const mix = value.match(/^color-mix\(in oklab,\s*(.+?)\s+([\d.]+)%,\s*(.+)\)$/);
  if (mix) {
    const p = +mix[2] / 100;
    const a = parseColor(mix[1]);
    const b = parseColor(mix[3]);
    if (b[3] === 0) return [a[0], a[1], a[2], a[3] * p]; // premultiplied mix with transparent
    const [la, lb] = [toOklab(a), toOklab(b)];
    return fromOklab([0, 1, 2].map((i) => la[i] * p + lb[i] * (1 - p)) as [number, number, number], 1);
  }
  throw new Error(`Unsupported colour: ${value}`);
}

/** Alpha-composites `top` over an opaque `base` (browsers blend in sRGB). */
function over(top: RGBA, base: RGBA): RGBA {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + base[i] * (1 - a)).concat(1) as RGBA;
}

function luminance([r, g, b]: RGBA): number {
  const [lr, lg, lb] = [r, g, b].map((c) => toLinear(c / 255));
  return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb;
}

function contrast(fg: RGBA, bg: RGBA): number {
  const [hi, lo] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT = ["foreground", "muted-foreground", "subtle-foreground", "positive", "negative", "warning", "info", "model"];
const SURFACES = ["background", "card", "popover", "sidebar", "muted", "secondary"];

/** [foreground, background, surface the background sits on (for translucent backgrounds)]. */
type Pair = [string, string, string?];

const textPairs: Pair[] = [
  ...TEXT.flatMap((fg) => SURFACES.map((bg): Pair => [fg, bg])),
  // Hover and selection overlays on cards and the sidebar, and the opaque table-row states.
  ...TEXT.flatMap((fg): Pair[] => [[fg, "accent", "card"], [fg, "selected", "card"], [fg, "table-row-hover"], [fg, "table-row-selected"]]),
  ["sidebar-foreground", "sidebar"],
  ["sidebar-foreground", "accent", "sidebar"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["accent-foreground", "accent", "card"],
  // Filled buttons and badges: text on its own fill.
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["destructive-foreground", "destructive"],
  ["brand-foreground", "brand"],
  ["button-brand-fg", "button-brand-bg"],
  ["positive", "positive-muted", "card"],
  ["negative", "negative-muted", "card"],
  ["warning", "warning-muted", "card"],
  ["model", "model-muted", "card"],
];

// Non-text UI and large text (≥ 3:1): focus ring, brand marks (logo, active-nav bar), input outlines.
const uiPairs: Pair[] = ["ring", "brand", "input"].flatMap((fg) => ["background", "card", "popover", "sidebar"].map((bg): Pair => [fg, bg]));

for (const theme of ["dark", "light"] as const) {
  describe(`${theme} theme`, () => {
    const vars = themeVars(theme);
    const color = (name: string) => parseColor(resolve(`var(--${name})`, vars));
    const ratio = ([fg, bg, base]: Pair) => {
      const surface = base ? over(color(bg), color(base)) : over(color(bg), color("background"));
      return contrast(over(color(fg), surface), surface);
    };

    test.each(textPairs)("text %s on %s (over %s) ≥ 4.5:1", (...pair) => {
      expect(ratio(pair as Pair)).toBeGreaterThanOrEqual(4.5);
    });
    test.each(uiPairs)("UI %s on %s ≥ 3:1", (...pair) => {
      expect(ratio(pair as Pair)).toBeGreaterThanOrEqual(3);
    });
  });
}

describe("contrast maths", () => {
  test("matches the ratios measured in the vault note", () => {
    expect(contrast(parseColor("#E9ECEF"), parseColor("#0A0B0D"))).toBeCloseTo(16.6, 1);
    expect(contrast(parseColor("#09934F"), parseColor("#FFFFFF"))).toBeCloseTo(3.96, 2);
    expect(contrast(parseColor("#FFFFFF"), parseColor("#000000"))).toBeCloseTo(21, 5);
  });

  test("each theme resolves its own values", () => {
    const value = (theme: Theme, name: string) => parseColor(resolve(`var(--${name})`, themeVars(theme)));
    expect(value("dark", "background")).toEqual([10, 11, 13, 1]);
    expect(value("light", "background")).toEqual([255, 255, 255, 1]);
    expect(value("light", "brand")).toEqual([9, 147, 79, 1]);
    expect(contrast(value("light", "brand"), value("light", "background"))).toBeLessThan(4.5); // UI-only in light
  });
});
