import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { Methodology } from "./methodology";
import { formatValue, methodology, sections, term, type MethodologyDoc } from "./model";

const render = (doc: MethodologyDoc) => renderToStaticMarkup(createElement(Methodology, { doc, description: "How every score is computed." }));
const lifecycle = methodology.scores.find((s) => s.id === "lifecycle-stage");

describe("Methodology", () => {
  test("renders Lifecycle Stage from the export: definition, thresholds and version hash", () => {
    if (lifecycle?.status !== "built") throw new Error("the export has no built Lifecycle Stage");
    const html = render(methodology);
    expect(html).toContain('<section id="lifecycle-stage"');
    expect(html).toContain(lifecycle.model_version);
    expect(html).toContain("One product&#x27;s stage on day t");
    const up = lifecycle.config.find((c) => c.name === "up")!;
    expect(html).toContain(`>${formatValue(up.value)}</td>`);
    expect(html).toContain("+20% week on week");
  });

  test("every section has its anchor, and the contents link to each one", () => {
    const html = render(methodology);
    for (const { id } of sections(methodology)) {
      expect(html).toContain(`id="${id}"`);
      expect(html).toContain(`href="#${id}"`);
    }
  });

  test("a score with no code is a not-built row with its phase and task, and no number", () => {
    const html = render(methodology);
    const card = html.slice(html.indexOf('aria-labelledby="not-built-title"'));
    expect(card).toContain("Pulso shows no number for these until their code ships.");
    const row = card.indexOf('id="risk"');
    const risk = card.slice(card.indexOf(">", row) + 1, card.indexOf("</li>", row)); // the row's content, not its classes
    expect(risk).toContain(">Risk &amp; Refund Risk</h3>");
    expect(risk).toContain(">Phase 5</span>");
    expect(risk.replace(/<[^>]+>/g, " ")).not.toMatch(/\d+\.\d|model_version/);
  });

  test("missing inputs read no source yet, never 0", () => {
    expect(render(methodology)).toContain("reads &quot;no source yet&quot;");
  });

  test("with no built score the page says so instead of an empty list", () => {
    const html = render({ ...methodology, scores: methodology.scores.filter((s) => s.status !== "built") });
    expect(html).toContain("No score is built yet");
    expect(html).not.toContain('id="lifecycle-stage"');
  });
});

describe("model", () => {
  test("a rule's name leads its item; a long prefix stays prose", () => {
    expect(term("dead · no sales: at most 1 unit")).toEqual(["dead · no sales", "at most 1 unit"]);
    expect(term("V7(t) = units over t−6..t")).toEqual([null, "V7(t) = units over t−6..t"]);
    expect(term("a sentence long enough that its first colon is not a rule name: x")[0]).toBeNull();
  });

  test("config values show four decimals with a true minus sign", () => {
    expect(formatValue(Math.log(0.8))).toBe("−0.2231");
    expect(formatValue(15)).toBe("15");
    expect(formatValue("001-abc")).toBe("001-abc");
  });
});
