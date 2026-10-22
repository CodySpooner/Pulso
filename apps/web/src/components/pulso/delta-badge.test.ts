import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { DeltaBadge } from "./delta-badge";

const render = (props: Parameters<typeof DeltaBadge>[0]) => renderToStaticMarkup(createElement(DeltaBadge, props));

describe("DeltaBadge", () => {
  test.each([null, undefined, Number.NaN, Infinity, -Infinity])("%s renders an em dash with its reason", (value) => {
    const html = render({ value, unit: "%", goodDirection: "down" });
    expect(html).toContain('title="No source yet"');
    expect(html).toContain('<span aria-hidden="true">—</span><span class="sr-only">No source yet</span>');
    expect(html).not.toMatch(/[▲▼±%0]|NaN|Infinity|text-positive|text-negative/);
  });

  test("the missing reason can name the gap", () => {
    expect(render({ value: null, missingReason: "No supplier matched yet" })).toContain('title="No supplier matched yet"');
  });

  test("a finite value keeps its glyph, sign, unit and tone", () => {
    const html = render({ value: -3.06, unit: "%", goodDirection: "down" });
    expect(html).toContain("text-positive");
    expect(html).toContain('<span aria-hidden="true" class="text-micro">▼</span>−3.1%</span>');
  });
});
