import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { Sparkline, sparkSegments } from "./sparkline";

const render = (values: (number | null)[]) => renderToStaticMarkup(createElement(Sparkline, { values }));

describe("Sparkline", () => {
  test("a null point breaks the line into separate polylines, never bridging the gap", () => {
    const html = render([1, 2, 3, null, null, 4, 5, 6]);
    expect(html.match(/<polyline/g)).toHaveLength(2);
    expect(sparkSegments([1, 2, 3, null, null, 4, 5, 6], 64, 20)).toHaveLength(2);
  });

  test("a value alone between gaps is a dot", () => {
    const html = render([1, 2, null, 3, null, 4, 5]);
    expect(html.match(/<polyline/g)).toHaveLength(2);
    expect(html.match(/<circle/g)).toHaveLength(1);
  });

  test("under 3 values is a dashed baseline, and the svg is hidden from screen readers", () => {
    const html = render([null, 4, null, 5, null]);
    expect(html).toContain('stroke-dasharray="2 3"');
    expect(html).not.toContain("<polyline");
    expect(html).toContain('aria-hidden="true"');
  });
});
