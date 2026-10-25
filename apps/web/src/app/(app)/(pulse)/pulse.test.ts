import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { LATEST, nothing, pulse, withStatus } from "../../../../e2e/pulse/data";
import { PulseCard } from "./cards";
import { cardOrder, dayParam, isBehind, isStale, sectionOf, seriesValues, shiftDay, sparkSegments, type CardId, type Pulse } from "./model";

const CARDS: CardId[] = ["emerging", "movers", "new_in_stores", "alerts", "watchlists", "suppliers", "search", "margins"];
const render = (id: CardId, p: Pulse) => renderToStaticMarkup(createElement(TooltipProvider, null, createElement(PulseCard, { id, pulse: p, index: 0, animate: false })));
/** The fixture with every section populated (it ships new launches and margins without a source, as with Shopify off). */
const full = (): Pulse => {
  const p = pulse();
  const launch = { listing_id: 7001, product: p.sections.emerging.items[0].product, title: "Moon lamp 3D print", store: "glowhaus.com", published_at: `${LATEST}T02:00:00Z`, as_of: `${LATEST}T05:00:00Z` };
  const margin = { product: p.sections.emerging.items[1].product, old_bps: 3120, new_bps: 2870, change_bps: -250, duty_not_set: true, supplier_listing_id: 4801, as_of: `${LATEST}T06:00:00Z` };
  const ok = { status: "ok" as const, reason: null };
  return { ...p, sections: { ...p.sections, new_in_stores: { ...p.sections.new_in_stores, ...ok, as_of: launch.as_of, items: [launch] }, margins: { ...p.sections.margins, ...ok, as_of: margin.as_of, items: [margin] } } };
};
const keys = (id: CardId) => (id === "movers" ? (["movers_up", "movers_down"] as const) : ([id] as const));
const set = (p: Pulse, id: CardId, status: "empty" | "no_source") => keys(id).reduce((acc, key) => withStatus(acc, key, status, `Reason for ${id} ${status}.`), p);

describe("each card in each status", () => {
  test.each(CARDS)("%s ok: its rows link to products, with its own as of, never a no-source state", (id) => {
    const html = render(id, full());
    expect(html).toContain('data-status="ok"');
    expect(html).toMatch(/href="\/(products|testing)[^"]*"/);
    expect(html).toMatch(/As of (\d\d:\d\d UTC|Oct \d+)/);
    expect(html).not.toContain("No source yet");
  });

  test.each(CARDS)("%s empty: says nothing happened and why, with no rows", (id) => {
    const html = render(id, set(full(), id, "empty"));
    expect(html).toContain('data-status="empty"');
    expect(html).toContain(`Reason for ${id} empty.`);
    expect(html).not.toContain("<li ");
    expect(html).not.toContain("No source yet");
    expect(html).toContain("As of —");
  });

  test.each(CARDS)("%s no source: says No source yet with the reason and Data Health, never a 0", (id) => {
    const html = render(id, set(full(), id, "no_source"));
    expect(html).toContain('data-status="no_source"');
    expect(html).toContain("No source yet");
    expect(html).toContain(`Reason for ${id} no_source.`);
    expect(html).toContain('href="/admin/data-health"');
    expect(html).not.toContain("<li ");
    expect(html.replace(/<[^>]+>/g, " ")).not.toMatch(/(^|\s)[−+]?0(\.0+)?%?(\s|$)/);
  });
});

describe("cards", () => {
  test("rows carry a signed delta with a glyph, and the hover says source and as of", () => {
    const html = render("emerging", pulse());
    expect(html).toContain("▲</span>+6.2");
    expect(html).toContain('title="Trend Score · as of Oct 21, 06:10 UTC"');
    expect(html).toContain("Rising");
  });

  test("movers start on Up with the toggle; falls stay off the Up list", () => {
    const html = render("movers", pulse());
    expect(html).toMatch(/aria-pressed="true".*?>Up</);
    expect(html).not.toContain("Mini waffle maker");
  });

  test.each([pulse(), withStatus(pulse(), "alerts", "empty", "No alert fired on this day.")])("the alerts card links the inbox", (p) => {
    const html = render("alerts", p);
    expect(html).toContain('href="/alerts"');
  });

  test("alerts list unread first with an unread count, and link each alert's product", () => {
    const html = render("alerts", pulse());
    expect(html).toContain("2 unread");
    expect(html.indexOf("Supplier ran out of stock")).toBeLessThan(html.indexOf("Freight fell"));
    expect(html).toContain('href="/products/3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b01?tab=suppliers"');
  });

  test("the watchlist shows sparklines, a stage entered on the day and a missing trend as —", () => {
    const html = render("watchlists", pulse());
    expect(html).toContain("<polyline");
    expect(html).toContain("Entered Rising on this day, from Emerging");
    expect(html).toContain('title="No comparable score the day before"');
    expect(html).toContain('stroke-dasharray="2 3"'); // two scored days: a dashed baseline, not a line
    expect(html).toContain('<select aria-label="Watchlist"');
  });

  test("a section older than 36 h before the cutoff is marked stale", () => {
    expect(render("search", pulse())).toContain("bg-warning");
    expect(render("emerging", pulse())).not.toContain("bg-warning");
  });
});

describe("model", () => {
  test("dayParam takes real YYYY-MM-DD days only", () => {
    expect(dayParam("2026-10-20")).toBe("2026-10-20");
    for (const raw of [null, "", "2026-1-2", "yesterday", "2026-13-40"]) expect(dayParam(raw)).toBeNull();
  });

  test("shiftDay crosses months and years in UTC", () => {
    expect(shiftDay("2026-11-01", -1)).toBe("2026-10-31");
    expect(shiftDay("2026-12-31", 1)).toBe("2027-01-01");
  });

  test("stale past 1.5 days before the cutoff; behind when the latest day is before yesterday", () => {
    expect(isStale("2026-10-20T11:59:00Z", "2026-10-22T00:00:00Z")).toBe(true);
    expect(isStale("2026-10-20T12:01:00Z", "2026-10-22T00:00:00Z")).toBe(false);
    expect(isStale(null, "2026-10-22T00:00:00Z")).toBe(false);
    const now = Date.parse("2026-10-22T14:00:00Z");
    expect(isBehind("2026-10-21", now)).toBe(false);
    expect(isBehind("2026-10-20", now)).toBe(true);
  });

  test("unread alerts lead, no-source sections go last, the rest keep their order", () => {
    expect(cardOrder(pulse().sections)).toEqual(["alerts", "emerging", "movers", "watchlists", "suppliers", "search", "new_in_stores", "margins"]);
    expect(cardOrder(nothing().sections)).toEqual(["alerts", "watchlists", "emerging", "movers", "new_in_stores", "suppliers", "search", "margins"]);
  });

  test("with Shopify off at least three sections are populated", () => {
    const p = pulse();
    expect(CARDS.filter((id) => sectionOf(p.sections, id).status === "ok").length).toBeGreaterThanOrEqual(3);
    expect(p.sections.new_in_stores.status).toBe("no_source");
  });

  test("the 14-day series breaks at a day without a score, never bridging it", () => {
    const values = seriesValues([{ day: "2026-10-08", value: 10 }, { day: "2026-10-10", value: 30 }, { day: "2026-10-11", value: 20 }], "2026-10-21");
    expect(values).toHaveLength(14);
    expect(values.slice(0, 4)).toEqual([10, null, 30, 20]);
    expect(sparkSegments(values, 64, 20)).toEqual(["1.0,19.0", "10.5,1.0 15.3,10.0"]);
  });
});
