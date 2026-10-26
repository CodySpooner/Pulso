import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { Methodology } from "./methodology";
import { every, formatValue, methodology, sections, span, term, type MethodologyDoc } from "./model";

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

  test("#confidence states the formula, the freshness rule and each source's cadence from the export", () => {
    const html = render(methodology);
    const section = html.slice(html.indexOf('<section id="confidence"'), html.indexOf('<section id="limitations"'));
    const { confidence } = methodology.contract;
    expect(section).toContain(confidence.formula.replace(/\.$/, ""));
    expect(section).toContain(">stale: </span>older, so it is missing");
    expect(section).not.toContain("Not built yet");
    const row = (source: string) => {
      const at = section.indexOf(`>${source}</code>`);
      return section.slice(at, section.indexOf("</tr>", at));
    };
    expect(row("cj")).toContain(">daily<");
    expect(row("cj")).toMatch(/>36 h<\/td>.*>3 d<\/td>$/);
    expect(row("google_trends")).toContain(">weekly<");
    expect(row("google_trends")).toMatch(/>10\.5 d<\/td>.*>21 d<\/td>$/);
    expect(row("trend")).toContain("score row");
  });

  test("with no cadence the section says every input counts as fresh instead of an empty table", () => {
    const { contract } = methodology;
    const html = render({ ...methodology, contract: { ...contract, confidence: { ...contract.confidence, cadence: [] } } });
    expect(html).toContain("No source has a cadence yet, so every input counts as fresh.");
    expect(html).not.toContain('aria-label="Source cadences"');
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

  test("a cadence reads daily or weekly, and an age under 2 days in hours", () => {
    expect([every(1), every(7), every(2)]).toEqual(["daily", "weekly", "every 2 d"]);
    expect([span(1.5), span(3), span(10.5), span(21)]).toEqual(["36 h", "3 d", "10.5 d", "21 d"]);
  });

  test("config values show four decimals with a true minus sign", () => {
    expect(formatValue(Math.log(0.8))).toBe("−0.2231");
    expect(formatValue(15)).toBe("15");
    expect(formatValue("001-abc")).toBe("001-abc");
  });
});
