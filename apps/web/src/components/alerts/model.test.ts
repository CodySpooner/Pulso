import { describe, expect, it } from "vitest";

import type { SearchResults } from "@/components/shell/palette-search";

import {
  badge,
  bellLabel,
  createBody,
  describeAlert,
  DRAFT,
  draftOf,
  entityHref,
  fieldErrors,
  FOREVER,
  gapSpan,
  groupByDay,
  lastEvaluation,
  mutedLabel,
  muteUntil,
  patchBody,
  pickerStatus,
  rulesLine,
  statusLine,
  targetOf,
  threshold,
  type Alert,
  type Draft,
  type Rule,
} from "./model";

const alert = (id: number, over: Partial<Alert> = {}): Alert => ({
  id,
  rule_id: null,
  type: "supplier_price_change",
  entity_type: "supplier_offer",
  entity_id: "4812",
  fired_at: "2026-10-25T06:00:00Z",
  payload: {},
  read_at: null,
  ...over,
});

describe("the bell's count", () => {
  it.each([
    [0, null],
    [1, "1"],
    [99, "99"],
    [100, "99+"],
    [1234, "99+"],
  ])("%i shows %j", (count, text) => expect(badge(count)).toBe(text));

  it("names the exact count, even past the badge's 99+", () => {
    expect(bellLabel(undefined)).toBe("Alerts");
    expect(bellLabel(0)).toBe("Alerts, none unread");
    expect(bellLabel(1)).toBe("Alerts, 1 unread");
    expect(bellLabel(120)).toBe("Alerts, 120 unread");
  });
});

describe("groupByDay", () => {
  const now = Date.parse("2026-10-25T14:00:00Z");

  it("splits Today and Earlier on the UTC day, keeping the API's order", () => {
    const rows = [alert(4, { fired_at: "2026-10-25T13:00:00Z" }), alert(3, { fired_at: "2026-10-25T00:00:00+00:00" }), alert(2, { fired_at: "2026-10-24T23:59:59Z" }), alert(1)];
    rows[3].fired_at = "2026-10-20T06:00:00Z";
    expect(groupByDay(rows, now).map((g) => [g.label, g.items.map((a) => a.id)])).toEqual([
      ["Today", [4, 3]],
      ["Earlier", [2, 1]],
    ]);
  });

  it("reads an offset as UTC: 20:00 −05:00 on the 24th is 01:00 UTC on the 25th", () => {
    expect(groupByDay([alert(1, { fired_at: "2026-10-24T20:00:00-05:00" })], now)).toEqual([{ label: "Today", items: [expect.objectContaining({ id: 1 })] }]);
  });

  it("drops an empty group", () => {
    expect(groupByDay([alert(1, { fired_at: "2026-10-01T06:00:00Z" })], now).map((g) => g.label)).toEqual(["Earlier"]);
    expect(groupByDay([], now)).toEqual([]);
  });
});

describe("describeAlert", () => {
  const money = (value: number) => ({ value, currency: "USD", as_of: "2026-10-25T05:00:00Z" });

  it("a price change: its sentence, signed change and old → new money", () => {
    const d = describeAlert(alert(1, { payload: { old: money(1240), new: { ...money(1390), source: "cj" }, threshold: { pct: 5 } } }));
    expect(d.title).toBe("Supplier price rose");
    expect(d.pct).toBeCloseTo(12.1, 1);
    expect(d.change).toBe("$12.40 → $13.90");
    expect(d.meta).toBe("CJ · offer 4812");
    expect(d.asOf).toBe("2026-10-25T05:00:00Z");
  });

  it("a freight drop and the stock flips", () => {
    expect(describeAlert(alert(1, { type: "freight_change", payload: { old: money(500), new: money(450) } }))).toMatchObject({ title: "Freight fell", pct: -10, change: "$5.00 → $4.50" });
    const flip = (from: boolean, to: boolean) => ({ old: { value: from }, new: { value: to, source: "cj" } });
    expect(describeAlert(alert(1, { type: "supplier_stock_out", payload: flip(true, false) }))).toMatchObject({ title: "Supplier ran out of stock", pct: null, change: "In stock → Out of stock" });
    expect(describeAlert(alert(1, { type: "back_in_stock", payload: flip(false, true) }))).toMatchObject({ title: "Supplier back in stock", change: "Out of stock → In stock" });
  });

  it("an unknown type or a payload without values still reads, with no change", () => {
    expect(describeAlert(alert(1, { type: "system.collector_blocked", entity_type: "source", entity_id: "cj" }))).toMatchObject({ title: "System collector blocked", pct: null, change: null, meta: "source cj" });
    expect(describeAlert(alert(1, { payload: { old: { value: "x" } } }))).toMatchObject({ pct: null, change: null });
  });

  it("score alerts (DEC-353): a velocity rise is good news in units /7d; a Saturation cross names its line", () => {
    const at = "2026-11-04T00:00:00+00:00";
    const product = { entity_type: "product", entity_id: "p-1" };
    const spike = { old: { value: 20, as_of: "2026-10-28T00:00:00+00:00" }, new: { value: 32.5, as_of: at, source: "cj" }, product: "Sunset lamp" };
    expect(describeAlert(alert(1, { type: "velocity_spike", ...product, payload: spike }))).toMatchObject({
      title: "Velocity spiked",
      pct: 62.5,
      good: "up",
      change: "20 → 32.5 /7d",
      meta: "CJ · Sunset lamp",
      asOf: at,
    });
    const cross = (direction: string) => ({ old: { value: 61 }, new: { value: 66.4, as_of: at }, threshold: { threshold: 65, direction }, product: "Sunset lamp" });
    expect(describeAlert(alert(1, { type: "saturation_cross", ...product, payload: cross("above") }))).toMatchObject({
      title: "Saturation rose above 65",
      pct: null,
      change: "61 → 66.4",
      meta: "Sunset lamp",
    });
    expect(describeAlert(alert(1, { type: "saturation_cross", payload: cross("below") })).title).toBe("Saturation fell below 65");
    expect(describeAlert(alert(1, { payload: { old: money(500), new: money(450) } })).good).toBe("down");
  });
});

describe("entityHref", () => {
  it("maps the payload's suppliers link to the Product Page's tab", () => {
    const id = "5e7a0c11-0000-4000-8000-000000000007";
    expect(entityHref(alert(1, { payload: { link: `/products/${id}/suppliers` } }))).toBe(`/products/${id}?tab=suppliers`);
    expect(entityHref(alert(1, { payload: { link: `/products/${id}` } }))).toBe(`/products/${id}`);
  });

  it("opens a test in its drawer and a product by its id; anything else has no page", () => {
    expect(entityHref(alert(1, { entity_type: "test", entity_id: "12" }))).toBe("/testing?test=12");
    expect(entityHref(alert(1, { entity_type: "product", entity_id: "p-1" }))).toBe("/products/p-1");
    expect(entityHref(alert(1))).toBeNull();
    expect(entityHref(alert(1, { payload: { link: "https://evil.example.test/" } }))).toBeNull();
  });
});

describe("rule status", () => {
  const now = Date.parse("2026-10-25T14:00:00Z");
  const rule = (last_evaluated_at: string | null) => ({ last_evaluated_at });

  it("the newest evaluation, stale past 26 h; none before the first", () => {
    expect(lastEvaluation([rule("2026-10-25T06:00:00Z"), rule(null), rule("2026-10-24T06:00:00+00:00")], now)).toEqual({ iso: "2026-10-25T06:00:00.000Z", stale: false });
    expect(lastEvaluation([rule("2026-10-24T11:59:00Z")], now)?.stale).toBe(true);
    expect(lastEvaluation([rule(null)], now)).toBeNull();
    expect(lastEvaluation([], now)).toBeNull();
  });

  it("counts the rules that are on and those with no source yet", () => {
    const r = (enabled: boolean, status: string | null) => ({ enabled, status });
    expect(rulesLine([])).toBe("No rule is on yet.");
    expect(rulesLine([r(false, "ok")])).toBe("No rule is on yet.");
    expect(rulesLine([r(true, "ok")])).toBe("1 rule is on.");
    expect(rulesLine([r(true, "no_source"), r(true, null), r(false, "no_source")])).toBe("2 rules are on, 1 with no source yet.");
  });

  it("a gap's span in UTC days", () => {
    expect(gapSpan({ reason: "gap", from: "2026-11-03T06:00:00Z", to: "2026-11-05T02:00:00Z" })).toBe("data gap Nov 3 → Nov 5");
    expect(gapSpan({ reason: "gap" })).toBe("data gap");
    expect(gapSpan(null)).toBe("data gap");
  });
});

// WF-4c (p4-27): the rule builder's payloads and the Rules tab's lines.
describe("the rule builder", () => {
  const product = { id: "5e7a0c11-0000-4000-8000-000000000007", name: "Sunset lamp" };
  const draft = (over: Partial<Draft> = {}): Draft => ({ ...DRAFT, target: "product", name: "", ...over });
  const saved = (over: Partial<Rule> = {}): Rule => ({
    id: "0a1e0000-0000-4000-8000-000000000001",
    name: "Lamp cost",
    type: "supplier_price_change",
    target_type: "supplier_offer",
    target_id: "4801",
    params: { pct: 8 },
    enabled: true,
    muted_until: null,
    armed: true,
    status: null,
    skipped: null,
    last_evaluated_at: null,
    created_at: "2026-10-20T00:00:00Z",
    product_id: product.id,
    product_name: product.name,
    watchlist_name: null,
    last_fired_at: null,
    ...over,
  });

  it("creates a supplier price rule on any of the product's suppliers, named from the sentence", () => {
    expect(createBody(draft(), product)).toEqual({
      name: "Sunset lamp: supplier price ±5%",
      type: "supplier_price_change",
      target_type: "product",
      target_id: product.id,
      params: { pct: 5 },
      enabled: true,
    });
  });

  it("targets one offer by its listing id and keeps a typed name, trimmed", () => {
    expect(createBody(draft({ target: "4801", type: "freight_change", pct: "12.5", name: "  Lamp freight " }), product)).toEqual({
      name: "Lamp freight",
      type: "freight_change",
      target_type: "supplier_offer",
      target_id: "4801",
      params: { pct: 12.5 },
      enabled: true,
    });
  });

  it.each([
    ["supplier_stock_out", "Sunset lamp: stock-out"],
    ["back_in_stock", "Sunset lamp: back in stock"],
  ] as const)("%s sends the API's default %, whatever was typed", (type, name) => {
    expect(createBody(draft({ type, pct: "9" }), product)).toEqual({ name, type, target_type: "product", target_id: product.id, params: { pct: 5 }, enabled: true });
  });

  it("passes a blank % on as 0, so the API's 422 says what's wrong", () => {
    expect(createBody(draft({ pct: " " }), product).params).toEqual({ pct: 0 });
  });

  it("edits only the name and, for price and freight, the %", () => {
    expect(patchBody(draft({ name: " Cost ±8% ", pct: "8" }), saved())).toEqual({ name: "Cost ±8%", params: { pct: 8 } });
    expect(patchBody(draft({ name: "Out", type: "supplier_stock_out" }), saved({ type: "supplier_stock_out", params: {} }))).toEqual({ name: "Out" });
  });

  it("reads a saved rule back into the sentence", () => {
    expect(draftOf(saved())).toEqual({ ...DRAFT, target: "4801", type: "supplier_price_change", pct: "8", name: "Lamp cost" });
    expect(draftOf(saved({ target_type: "test", target_id: null, type: "supplier_stock_out", params: {} }))).toEqual({ ...DRAFT, target: "product", type: "supplier_stock_out", pct: "5", name: "Lamp cost" });
    expect(draftOf(saved({ type: "velocity_spike", params: { pct: 80, window_days: 7, min_volume: 4 } }))).toMatchObject({ pct: "80", minVolume: "4" });
    expect(draftOf(saved({ type: "saturation_cross", params: { threshold: 30, direction: "below" } }))).toMatchObject({ threshold: "30", direction: "below" });
    expect(draftOf(saved({ type: "velocity_spike", params: {} })).pct).toBe("50");
  });

  it("score rules (DEC-353): a velocity spike on the product, a Saturation cross on a watchlist", () => {
    expect(createBody(draft({ type: "velocity_spike", pct: "60", minVolume: "15" }), product)).toEqual({
      name: "Sunset lamp: velocity +60%",
      type: "velocity_spike",
      target_type: "product",
      target_id: product.id,
      params: { pct: 60, min_volume: 15 },
      enabled: true,
    });
    expect(createBody(draft({ type: "saturation_cross", target: "watchlist:w-1", threshold: "35", direction: "below" }), product)).toEqual({
      name: "Sunset lamp: saturation below 35",
      type: "saturation_cross",
      target_type: "watchlist",
      target_id: "w-1",
      params: { threshold: 35, direction: "below" },
      enabled: true,
    });
    const spike = saved({ type: "velocity_spike", target_type: "product", target_id: product.id });
    expect(patchBody(draft({ type: "velocity_spike", pct: "70", minVolume: "", name: "Spike" }), spike)).toEqual({ name: "Spike", params: { pct: 70, min_volume: 0 } });
    expect(patchBody(draft({ type: "saturation_cross", name: "Crowded" }), saved({ type: "saturation_cross" }))).toEqual({ name: "Crowded", params: { threshold: 65, direction: "above" } });
  });

  it("puts each 422 message next to its field", () => {
    const problem = (errors: object[], detail = "Invalid request.") => ({ type: "about:blank", title: "Unprocessable", status: 422, code: "validation_error", detail, request_id: "r", errors });
    expect(fieldErrors(problem([{ loc: ["body", "params", "min_volume"], msg: "≥ 0", type: "x" }, { loc: ["body", "params", "threshold"], msg: "≤ 100", type: "x" }]))).toEqual({ min_volume: "≥ 0", threshold: "≤ 100" });
    expect(fieldErrors({ ...problem([], "Supplier offer not found."), status: 404, code: "not_found" })).toEqual({ form: "Supplier offer not found." });
    expect(fieldErrors(new TypeError("fetch failed")).form).toMatch(/didn’t answer/);
  });

  // imp-585: Pydantic's range, type and length messages, by their `type`, in words per field.
  it.each([
    [["body", "params", "pct"], "greater_than", "Input should be greater than 0", "Enter a % above 0, up to 1,000."],
    [["body", "params", "pct"], "less_than_equal", "Input should be less than or equal to 1000", "Enter a % above 0, up to 1,000."],
    [["body", "params", "min_volume"], "greater_than_equal", "Input should be greater than or equal to 0", "Enter 0 to 1,000,000 units."],
    [["body", "params", "threshold"], "less_than_equal", "Input should be less than or equal to 100", "Saturation runs from 0 to 100."],
    [["body", "params", "threshold"], "missing", "Field required", "Saturation runs from 0 to 100."],
    [["body", "params", "threshold"], "float_parsing", "Input should be a valid number, unable to parse string as a number", "Saturation runs from 0 to 100."],
    [["body", "params", "direction"], "literal_error", "Input should be 'above' or 'below'", "Choose above or below."],
    [["body", "name"], "string_too_short", "String should have at least 1 character", "Give the rule a name, up to 120 characters."],
    [["body", "name"], "string_too_long", "String should have at most 120 characters", "Give the rule a name, up to 120 characters."],
  ])("says %j's %s in words", (loc, type, msg, copy) => {
    const name = loc.at(-1) as string;
    expect(fieldErrors({ type: "about:blank", title: "Unprocessable", status: 422, code: "validation_error", detail: "Invalid request.", request_id: "r", errors: [{ loc, msg, type }] })).toEqual({ [name]: copy });
  });

  it("keeps the API's text for any other message", () => {
    const problem = (errors: object[]) => ({ type: "about:blank", title: "Unprocessable", status: 422, code: "validation_error", detail: "Invalid request.", request_id: "r", errors });
    expect(fieldErrors(problem([{ loc: ["body", "params", "pct"], msg: "Not a param of this rule type", type: "extra" }]))).toEqual({ pct: "Not a param of this rule type" });
    expect(fieldErrors(problem([{ loc: ["body", "name"], msg: "String should match pattern '^[^\\x00]*$'", type: "string_pattern_mismatch" }]))).toEqual({ name: "String should match pattern '^[^\\x00]*$'" });
    expect(fieldErrors(problem([{ loc: ["body", "params", "window_days"], msg: "Input should be 7", type: "literal_error" }]))).toEqual({ form: "Input should be 7" });
  });

  it("names a rule's target, linking its product", () => {
    expect(targetOf(saved())).toEqual({ label: "Sunset lamp", detail: "offer 4801", href: `/products/${product.id}?tab=suppliers` });
    expect(targetOf(saved({ target_type: "product", target_id: product.id }))).toMatchObject({ label: "Sunset lamp", detail: "any supplier" });
    expect(targetOf(saved({ target_type: "test", target_id: null, product_id: null, product_name: null }))).toEqual({ label: "Products in Testing", detail: "every open test", href: "/testing" });
    const scoreOn = { target_type: "product", target_id: product.id };
    expect(targetOf(saved({ type: "velocity_spike", ...scoreOn }))).toEqual({ label: "Sunset lamp", detail: "this product", href: `/products/${product.id}?tab=trends` });
    expect(targetOf(saved({ type: "saturation_cross", ...scoreOn })).href).toBe(`/products/${product.id}`);
    const listed = { type: "saturation_cross", target_type: "watchlist", target_id: "w-1", product_id: null, product_name: null };
    expect(targetOf(saved({ ...listed, watchlist_name: "Pets" }))).toEqual({ label: "Pets", detail: "every product on it", href: "/watchlists?list=w-1" });
  });

  it("shows the threshold only where a rule has one", () => {
    expect(threshold(saved())).toBe("±8%");
    expect(threshold(saved({ type: "back_in_stock", params: {} }))).toBeNull();
    expect(threshold(saved({ type: "velocity_spike", params: { pct: 50, window_days: 7, min_volume: 10 } }))).toBe("+50% · ≥10 /7d");
    expect(threshold(saved({ type: "saturation_cross", params: { threshold: 35, direction: "below" } }))).toBe("below 35");
  });
});

describe("a rule's status line", () => {
  const now = Date.parse("2026-10-25T14:00:00Z");
  const r = (status: Rule["status"], over: Partial<Pick<Rule, "skipped" | "last_evaluated_at">> = {}) => ({ status, skipped: null, last_evaluated_at: null, ...over });

  it.each([
    [r(null), "Not evaluated yet", "muted"],
    [r("no_source", { last_evaluated_at: "2026-10-25T06:00:00Z" }), "No source yet", "muted"],
    [r("skipped", { skipped: { reason: "gap", from: "2026-10-19T00:00:00Z", to: "2026-10-21T00:00:00Z" } }), "1 evaluation skipped: data gap Oct 19 → Oct 21", "warning"],
    [r("ok", { last_evaluated_at: "2026-10-25T06:00:00Z" }), "Evaluated 8h ago", "ok"],
  ])("%j", (rule, text, tone) => expect(statusLine(rule, now)).toEqual({ text, tone }));
});

describe("mute", () => {
  const now = Date.parse("2026-10-25T14:00:00Z");

  it("mutes for 24 h, 7 d or until unmuted", () => {
    expect(muteUntil(24, now)).toBe("2026-10-26T14:00:00.000Z");
    expect(muteUntil(168, now)).toBe("2026-11-01T14:00:00.000Z");
    expect(muteUntil(null, now)).toBe(FOREVER);
  });

  it("says until when, and nothing once it has passed", () => {
    expect(mutedLabel(null, now)).toBeNull();
    expect(mutedLabel("2026-10-25T13:59:00Z", now)).toBeNull();
    expect(mutedLabel("2026-10-26T14:00:00Z", now)).toBe("Muted until Oct 26, 14:00 UTC");
    expect(mutedLabel(FOREVER, now)).toBe("Muted until you unmute");
  });
});

// imp-527: the builder's product picker, from the palette's search counting products only.
describe("the product picker's states", () => {
  const none: SearchResults = { products: [], stores: [], suppliers: [], catalog_empty: false };
  const lamp = { id: "p-1", title: "Sunset lamp", category: null, match: { field: "title", text: "Sunset lamp", kind: "prefix" } } as const;
  const results = (products: SearchResults["products"], stale = false) => ({ kind: "results", results: { ...none, products }, stale }) as const;

  it.each([
    ["under 2 characters", { kind: "off" }, { kind: "hint", text: "Type 2 or more characters to search products." }],
    ["loading", { kind: "loading" }, { kind: "loading", text: "Searching products…", busy: true }],
    ["1 result", results([lamp]), { kind: "results", text: "1 product for “lamp”" }],
    ["2 results", results([lamp, { ...lamp, id: "p-2" }]), { kind: "results", text: "2 products for “lamp”" }],
    // stale: an earlier query's products stay under a spinner, and the live region waits
    ["stale", results([lamp], true), { kind: "results", text: "", busy: true }],
    // the search matched only stores or suppliers
    ["stores only", results([]), { kind: "empty", text: "No products match “lamp”", detail: "Try fewer words, or part of a listing’s title." }],
    ["stores only, stale", results([], true), { kind: "loading", text: "Searching products…", busy: true }],
    ["empty", { kind: "empty" }, { kind: "empty", text: "No products match “lamp”", detail: "Try fewer words, or part of a listing’s title." }],
    ["no source yet", { kind: "no-source" }, { kind: "no-source", text: "No products collected yet", detail: "Search fills in once the collectors have run." }],
    ["error", { kind: "error" }, { kind: "error", text: "Search unavailable", detail: "Retry, or choose Create alert on a product’s page." }],
  ] as const)("%s", (_, view, status) => expect(pickerStatus(view, "lamp")).toEqual(status));

  it("says how long a pasted URL is", () => {
    expect(pickerStatus({ kind: "too-long" }, "x".repeat(130))).toEqual({ kind: "too-long", text: "Too long to search: 130 characters", detail: "Up to 100. Try a few words of the title." });
  });
});
