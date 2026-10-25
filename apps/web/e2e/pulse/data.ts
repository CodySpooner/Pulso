import type { components } from "../../src/lib/api/schema";

// Fixture GET /v1/pulse responses (DEC-337) for the Daily Pulse Vitest and e2e tests and screenshots, never a database
// restore. As the API answers with the Shopify crawler off (DEC-261): new launches and margins have no source; the rest
// come from scores, alerts, watchlists, CJ and Google Trends. Every time is on the requested day, so a day reads as its own.

type S = components["schemas"];
export type Pulse = S["Pulse"];

/** The latest scored day: the day before Data Health's pinned NOW (2026-10-22T14:00Z). */
export const LATEST = "2026-10-21";

const id = (n: number) => `3f6c1e52-8a7d-4b0e-9c21-5d4e8f7a6b${String(n).padStart(2, "0")}`;
const NAMES = [
  "Sunset projection lamp with 16 colour modes",
  "Magnetic cable organiser, 6 pack",
  "Portable neck fan, bladeless",
  "Self-cleaning slicker brush",
  "Cloud ice cube tray, silicone",
  "LED shower head with 3 colours",
  "Posture corrector, adjustable",
  "Mini waffle maker, 4 inch",
  "Car seat gap filler, PU leather",
  "Electric spin scrubber, cordless",
];
const ref = (n: number): S["Ref"] => ({ id: id(n), name: NAMES[n], image_url: n % 3 === 2 ? null : `https://cdn.example.test/product-${n}.svg` });

export function pulse(day = LATEST): Pulse {
  const at = (hh: number, mm = 0, days = 0) => new Date(Date.parse(`${day}T00:00:00Z`) + (days * 24 + hh) * 3_600_000 + mm * 60_000).toISOString();
  const shift = Number(day.slice(-2)) % 3; // a little different every day
  const move = (old: number, change: number): S["ScoreMove"] => ({ old, new: +(old + change).toFixed(1), change, as_of: at(6, 10) });
  const ok = <T,>(items: T[], sources: string[], as_of: string) => ({ status: "ok" as const, as_of, sources, reason: null, items });
  const alert = (n: number, type: string, hh: number, payload: Record<string, unknown>, read = false): S["AlertOut"] => ({
    id: 900 + n, rule_id: null, type, entity_type: "supplier_offer", entity_id: String(4800 + n), fired_at: at(hh, 15),
    payload: { link: `/products/${id(n)}/suppliers`, ...payload }, read_at: read ? at(hh + 1) : null,
  });
  const usd = (value: number, hh: number) => ({ value, currency: "USD", as_of: at(hh), source: "cj", raw_payload_id: 70_000 + value });
  const series = (base: number, step: number, gap?: number): S["TrendPoint"][] =>
    Array.from({ length: 14 }, (_, i) => i)
      .filter((i) => i !== gap)
      .map((i) => ({ day: at(0, 0, i - 13).slice(0, 10), value: +(base + step * i + ((i * 7) % 5) - 2).toFixed(1), as_of: at(6, 10, i - 13) }));
  const watched = (n: number, base: number, step: number, over: Partial<S["WatchedProduct"]> = {}): S["WatchedProduct"] => ({
    product: ref(n), added_at: at(9, 0, -20), trend: move(+(base + step * 12).toFixed(1), step), stage: "rising", stage_before: "rising", alerts: [],
    series: series(base, step), ...over,
  });

  return {
    day,
    cutoff: at(24),
    sections: {
      emerging: ok(
        [
          { product: ref(0), value: 71.4 - shift, stage: "rising", since_yesterday: move(65.2 - shift, 6.2), model_version: "trend-v0", as_of: at(6, 10) },
          { product: ref(2), value: 64.8, stage: "emerging", since_yesterday: move(58.1, 6.7), model_version: "trend-v0", as_of: at(6, 10) },
          { product: ref(4), value: 61.2, stage: "rising", since_yesterday: move(61.6, -0.4), model_version: "trend-v0", as_of: at(6, 10) },
          { product: ref(6), value: 55.9, stage: "emerging", since_yesterday: null, model_version: "trend-v0", as_of: at(6, 10) },
          { product: ref(8), value: 52.3, stage: "emerging", since_yesterday: move(49.9, 2.4), model_version: "trend-v0", as_of: at(6, 10) },
        ],
        ["trend", "lifecycle"],
        at(6, 10),
      ),
      movers_up: ok(
        [
          { product: ref(2), model_version: "trend-v0", ...move(58.1, 6.7 + shift) },
          { product: ref(0), model_version: "trend-v0", ...move(65.2, 6.2) },
          { product: ref(8), model_version: "trend-v0", ...move(49.9, 2.4) },
          { product: ref(5), model_version: "trend-v0", ...move(33.0, 1.8) },
        ],
        ["trend"],
        at(6, 10),
      ),
      movers_down: ok(
        [
          { product: ref(7), model_version: "trend-v0", ...move(47.5, -8.3) },
          { product: ref(3), model_version: "trend-v0", ...move(39.2, -3.1) },
          { product: ref(4), model_version: "trend-v0", ...move(61.6, -0.4) },
        ],
        ["trend"],
        at(6, 10),
      ),
      new_in_stores: { status: "no_source", as_of: null, sources: ["shopify_stores"], reason: "The Shopify store crawler is off.", items: [] },
      alerts: {
        ...ok(
          [
            alert(1, "supplier_stock_out", 9, { old: { value: true, as_of: at(-15) }, new: { value: false, as_of: at(8, 40), source: "cj", raw_payload_id: 71_001 } }),
            alert(3, "supplier_price_change", 7, { old: usd(1240, -20), new: usd(1390, 6), threshold: { pct: 5 } }),
            alert(5, "freight_change", 4, { old: usd(500, -30), new: usd(450, 3), threshold: { pct: 5 } }, true),
          ],
          ["alerts"],
          at(9, 15),
        ),
        unread: 2,
      },
      watchlists: ok(
        [
          {
            id: "0a1e0000-0000-4000-8000-0000000000a1", name: "Main", item_count: 4, as_of: at(6, 10),
            items: [
              watched(0, 52, 1.5, { stage_before: "emerging", alerts: ["supplier_price_change"] }),
              watched(1, 40, -0.8, { stage: "peaking", stage_before: "peaking" }),
              watched(5, 30, 0.2, { stage: "emerging", stage_before: "emerging", series: series(30, 0.2, 9) }),
              watched(9, 20, 0, { trend: null, stage: null, stage_before: null, series: series(20, 0).slice(-2) }),
            ],
          },
          { id: "0a1e0000-0000-4000-8000-0000000000a2", name: "Q4 gifts", item_count: 1, as_of: at(6, 10), items: [watched(7, 48, -1.1, { stage: "declining", stage_before: "peaking" })] },
        ],
        ["trend", "lifecycle", "alerts"],
        at(6, 10),
      ),
      margins: { status: "no_source", as_of: null, sources: ["workspace_product_economics"], reason: "No market price yet: a margin needs a store price and a supplier price.", items: [] },
      suppliers: ok(
        [
          { listing_id: 4801, product: ref(1), title: "Magnetic Cable Clips 6pcs Desk Organiser", source: "cj", currency: null, old_price_minor: null, new_price_minor: null, price_change_pct: null, was_in_stock: true, in_stock: false, raw_payload_id: 71_001, as_of: at(8, 40) },
          { listing_id: 4803, product: ref(3), title: "Pet Grooming Self Cleaning Slicker Brush", source: "cj", currency: "USD", old_price_minor: 1240, new_price_minor: 1390, price_change_pct: 12.1, was_in_stock: null, in_stock: null, raw_payload_id: 71_003, as_of: at(6) },
          { listing_id: 4806, product: ref(6), title: "Adjustable Posture Corrector Back Brace", source: "cj", currency: "USD", old_price_minor: 890, new_price_minor: 840, price_change_pct: -5.6, was_in_stock: null, in_stock: null, raw_payload_id: 71_006, as_of: at(5, 30) },
          { listing_id: 4809, product: null, title: "Silicone Ice Tray Cloud Shape 2pcs", source: "cj", currency: null, old_price_minor: null, new_price_minor: null, price_change_pct: null, was_in_stock: false, in_stock: true, raw_payload_id: 71_009, as_of: at(4, 50) },
        ],
        ["cj"],
        at(8, 40),
      ),
      search: ok(
        [
          { product: ref(2), slope: 0.531, change_pct: 70.1, keywords: 3, as_of: at(3, 0, -1) },
          { product: ref(0), slope: 0.262, change_pct: 30.0, keywords: 2, as_of: at(3, 0, -1) },
          { product: ref(7), slope: -0.223, change_pct: -20.0, keywords: 1, as_of: at(3, 0, -1) },
          { product: ref(4), slope: 0.095, change_pct: 10.0, keywords: 2, as_of: at(3, 0, -1) },
        ],
        ["google_trends"],
        at(3, 0, -1),
      ),
    },
  };
}

/** The same day with one section quiet (fed, nothing on the day) or without a source, as the API words them. */
export function withStatus(p: Pulse, key: keyof Pulse["sections"], status: "empty" | "no_source", reason = `${status} reason for ${key}`): Pulse {
  return { ...p, sections: { ...p.sections, [key]: { ...p.sections[key], status, as_of: null, reason, items: [], ...(key === "alerts" && { unread: 0 }) } } };
}

const NONE: Record<keyof Pulse["sections"], [status: "empty" | "no_source", reason: string]> = {
  emerging: ["no_source", "No Trend Score for this day yet: the nightly job hasn't scored it."],
  movers_up: ["no_source", "No Trend Score for this day yet: the nightly job hasn't scored it."],
  movers_down: ["no_source", "No Trend Score for this day yet: the nightly job hasn't scored it."],
  new_in_stores: ["no_source", "The Shopify store crawler is off."],
  alerts: ["empty", "No alert fired on this day."],
  watchlists: ["empty", "Watch products with W to see them here."],
  margins: ["no_source", "No market price yet: a margin needs a store price and a supplier price."],
  suppliers: ["no_source", "No supplier offer observed yet."],
  search: ["no_source", "No search interest for this day: no confirmed keyword has 12 weeks of Trends."],
};

/** An empty database: every section empty or no source, in the API's words (its test e). */
export function nothing(day = LATEST): Pulse {
  return Object.entries(NONE).reduce((p, [key, [status, reason]]) => withStatus(p, key as keyof Pulse["sections"], status, reason), pulse(day));
}
