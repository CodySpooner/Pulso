import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { describe, expect, test, vi } from "vitest";

import { breakEven, describeChange, moved, moveOptions, spendBar, staleMetrics, testDay, type Page, type Test } from "./model";

const NOW = Date.parse("2026-10-25T12:00:00Z");
const test_ = (id: number, over: Partial<Test> = {}): Test => ({
  id,
  product_id: `0000000${id}-0000-4000-8000-000000000000`,
  product_title: `Product ${id}`,
  product_image_url: null,
  stage: "idea",
  started_on: null,
  ended_on: null,
  currency: "USD",
  ad_spend_minor: 0,
  revenue_minor: 0,
  orders: 0,
  cpa_minor: null,
  roas: null,
  notes: null,
  kill_reason: null,
  start_snapshot: null,
  break_even_cpa_minor: null,
  stop_loss_minor: null,
  signal: null,
  signal_reason: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
  ...over,
});
const board = (): Page => ({
  items: [test_(3), test_(2, { stage: "killed", kill_reason: "saturated" }), test_(1, { stage: "killed", kill_reason: "other" })],
  next_cursor: null,
  kill_reasons: { saturated: 1, other: 1 },
});

describe("moved", () => {
  test("into Killed: the stage, the reason and the count", () => {
    const page = moved(board(), { id: 3, stage: "killed", kill_reason: "saturated" });
    expect(page.items[0]).toMatchObject({ id: 3, stage: "killed", kill_reason: "saturated" });
    expect(page.kill_reasons).toEqual({ saturated: 2, other: 1 });
  });

  test("out of Killed: the reason clears and a count that reaches 0 drops out, as the API omits it", () => {
    const page = moved(board(), { id: 1, stage: "researching" });
    expect(page.items[2]).toMatchObject({ stage: "researching", kill_reason: null });
    expect(page.kill_reasons).toEqual({ saturated: 1 });
  });

  test("Killed to Killed with a new reason moves one count", () => {
    expect(moved(board(), { id: 1, stage: "killed", kill_reason: "saturated" }).kill_reasons).toEqual({ saturated: 2 });
  });

  test("leaves the other tests and an unknown id alone, and never mutates the page", () => {
    const before = board();
    const copy = structuredClone(before);
    expect(moved(before, { id: 3, stage: "testing" }).items.slice(1)).toEqual(copy.items.slice(1));
    expect(moved(before, { id: 99, stage: "winner" })).toEqual(copy);
    expect(before).toEqual(copy);
  });
});

describe("moveOptions", () => {
  const KEY = ["get", "/v1/tests"];
  const setup = (send: () => Promise<Test>) => {
    const client = new QueryClient();
    client.setQueryData(KEY, board());
    const observer = new MutationObserver(client, moveOptions(client, KEY, send));
    return { client, observer, page: () => client.getQueryData<Page>(KEY)! };
  };

  test("moves at once, before the API answers", async () => {
    let answer!: (t: Test) => void;
    const { observer, page } = setup(() => new Promise((resolve) => (answer = resolve)));
    const done = observer.mutate({ id: 3, stage: "killed", kill_reason: "other" });
    await vi.waitFor(() => expect(answer).toBeDefined()); // the API has the request
    expect(page().items[0].stage).toBe("killed");
    expect(page().kill_reasons.other).toBe(2);
    answer(test_(3, { stage: "killed", kill_reason: "other" }));
    await done;
  });

  test("a failed move rolls back that card and its count only", async () => {
    let fail!: (e: unknown) => void;
    const { client, observer, page } = setup(() => new Promise((_, reject) => (fail = reject)));
    const done = observer.mutate({ id: 3, stage: "killed", kill_reason: "other" }).catch(() => null);
    await vi.waitFor(() => expect(fail).toBeDefined());
    expect(page().items[0].stage).toBe("killed");
    // Another move lands while this one is in flight; the rollback must keep it.
    client.setQueryData(KEY, moved(page(), { id: 2, stage: "winner" }));
    fail({ status: 503 });
    await done;
    expect(page().items.map((t) => [t.id, t.stage, t.kill_reason])).toEqual([
      [3, "idea", null],
      [2, "winner", null],
      [1, "killed", "other"],
    ]);
    expect(page().kill_reasons).toEqual({ other: 1 });
    expect(observer.getCurrentResult().isError).toBe(true);
  });
});

describe("breakEven", () => {
  const snapshot = { complete: true, price_minor: 3999, landed_cost_minor: 1420, margin_minor: 2433, missing: [], captured_at: "2026-10-21T09:00:00Z" };

  test("reads the start snapshot: break-even CPA is its margin, ROAS is price over it", () => {
    expect(breakEven(test_(1, { start_snapshot: snapshot }))).toEqual({ price: 3999, landed: 1420, cpa: 2433, roas: 3999 / 2433, capturedAt: "2026-10-21T09:00:00Z" });
  });

  test("not started, incomplete, or a margin of 0 or less", () => {
    expect(breakEven(test_(1))).toBeNull();
    expect(breakEven(test_(1, { start_snapshot: { ...snapshot, complete: false, margin_minor: null } }))).toBe("incomplete");
    expect(breakEven(test_(1, { start_snapshot: { ...snapshot, margin_minor: -50 } }))).toMatchObject({ cpa: -50, roas: null });
  });
});

test("staleMetrics: a Testing card not updated for over 48 h", () => {
  const at = (hours: number) => new Date(NOW - hours * 3_600_000).toISOString();
  expect(staleMetrics(test_(1, { stage: "testing", updated_at: at(49) }), NOW)).toBe(true);
  expect(staleMetrics(test_(1, { stage: "testing", updated_at: at(47) }), NOW)).toBe(false);
  expect(staleMetrics(test_(1, { stage: "idea", updated_at: at(200) }), NOW)).toBe(false);
});

describe("the Testing card's day and spend bar (DEC-340)", () => {
  test("day 1 is the UTC start date; none before a start or outside Testing", () => {
    expect(testDay(test_(1, { stage: "testing", started_on: "2026-10-25" }), NOW)).toBe(1);
    expect(testDay(test_(1, { stage: "testing", started_on: "2026-10-19" }), NOW)).toBe(7);
    expect(testDay(test_(1, { stage: "testing", started_on: "2026-10-26" }), NOW)).toBeNull();
    expect(testDay(test_(1, { stage: "winner", started_on: "2026-10-19" }), NOW)).toBeNull();
  });

  test("the worked example: spend against a $48.66 stop-loss at two thirds of the track", () => {
    const at = (spend: number) => spendBar(test_(1, { stage: "testing", ad_spend_minor: spend, stop_loss_minor: 4866 }));
    expect(at(0)).toEqual({ fill: 0, line: "$48.66", past: false });
    expect(at(4865)).toMatchObject({ past: false });
    expect(at(4866)).toEqual({ fill: 2 / 3, line: "$48.66", past: true });
    expect(at(10 ** 6)?.fill).toBe(1); // the bar stops at the track's end
    expect(spendBar(test_(1, { stage: "testing", ad_spend_minor: 500 }))).toBeNull(); // no break-even
  });
});

describe("describeChange", () => {
  test("money: old → new with a signed delta, a cost rise red ▲ and a break-even fall red ▼", () => {
    expect(describeChange({ input: "freight_minor", old: 400, new: 500 })).toEqual({ label: "Freight", old: "$4.00", new: "$5.00", delta: { glyph: "▲", text: "+$1.00", tone: "negative" } });
    expect(describeChange({ input: "margin_minor", old: 2253, new: 2103 })).toEqual({ label: "Break-even CPA", old: "$22.53", new: "$21.03", delta: { glyph: "▼", text: "−$1.50", tone: "negative" } });
    expect(describeChange({ input: "goods_minor", old: 1000, new: 900 }).delta).toEqual({ glyph: "▼", text: "−$1.00", tone: "positive" });
  });

  test("rates in points, a quote without a delta, and a value missing then or now", () => {
    expect(describeChange({ input: "duty_bps", old: 2000, new: 2500 })).toEqual({ label: "Duty rate", old: "20%", new: "25%", delta: { glyph: "▲", text: "+5 pts", tone: "negative" } });
    expect(describeChange({ input: "payment_fee_bps", old: 290, new: 350 }).delta?.text).toBe("+0.6 pts");
    expect(describeChange({ input: "freight_quote_id", old: 12, new: 15 })).toEqual({ label: "Freight quote", old: "#12", new: "#15", delta: null });
    expect(describeChange({ input: "freight_minor", old: 400, new: null })).toEqual({ label: "Freight", old: "$4.00", new: null, delta: null });
    expect(describeChange({ input: "price_minor", old: null, new: 3999 })).toMatchObject({ old: null, new: "$39.99", delta: null });
  });
});
