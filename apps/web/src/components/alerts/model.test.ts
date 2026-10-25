import { describe, expect, it } from "vitest";

import { badge, bellLabel, describeAlert, entityHref, gapSpan, groupByDay, lastEvaluation, rulesLine, type Alert } from "./model";

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
