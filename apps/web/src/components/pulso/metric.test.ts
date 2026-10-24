import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { Metric, ProvenanceCard, type Stat } from "./metric";

const NOW = Date.parse("2026-10-24T12:00:00Z");
const sourced: Stat = {
  value: 2400, source: "shopify_stores", source_name: "Shopify stores", as_of: "2026-10-24T06:04:00Z",
  raw_payload_id: 77, method: null, stale: false,
};
const missing: Stat = { value: null, reason: "No supplier listing matched yet." };
const usd = (minor: number) => `$${(minor / 100).toFixed(2)}`;

const card = (stat: Stat) => renderToStaticMarkup(createElement(ProvenanceCard, { stat, label: "Lowest price", now: NOW }));
const metric = (stat: Stat) =>
  renderToStaticMarkup(createElement(TooltipProvider, null, createElement(Metric, { stat, label: "Lowest price", format: usd, now: NOW })));

describe("Metric", () => {
  test("a sourced number is a focusable button in tabular numerals, named with its label", () => {
    const html = metric(sourced);
    expect(html).toMatch(/^<button[^>]*type="button"/);
    expect(html).toContain('aria-label="Lowest price: $24.00"');
    expect(html).toContain("tabular-nums");
    expect(html).toContain(">$24.00</button>");
  });

  test("a stat nothing backs reads No source yet, never 0", () => {
    const html = metric(missing);
    expect(html).toContain(">No source yet</button>");
    expect(html).not.toMatch(/>\$?0(\.00)?</);
  });
});

describe("ProvenanceCard", () => {
  test("shows the source, the UTC as-of with its age, and the raw payload id to select", () => {
    const html = card(sourced);
    expect(html).toContain("<dd>Shopify stores</dd>");
    expect(html).toContain('<time dateTime="2026-10-24T06:04:00Z">Oct 24, 06:04 UTC</time> · 5h ago');
    expect(html).toContain('<dd class="font-mono select-all">#77</dd>');
    expect(html).not.toContain("Method");
    expect(html).not.toContain("Stale");
  });

  test("an estimate names its method; an old value says stale in words, not colour alone", () => {
    const html = card({ ...sourced, method: "updated_at bumps (lower bound)", stale: true });
    expect(html).toContain("<dd>Estimate · updated_at bumps (lower bound)</dd>");
    expect(html).toMatch(/text-warning">.*Stale<\/span>/);
  });

  test("no source yet carries the reason, and no as-of or payload", () => {
    const html = card(missing);
    expect(html).toContain("No source yet. No supplier listing matched yet.");
    expect(html).not.toContain("<time");
    expect(html).not.toContain("Raw payload");
  });
});
