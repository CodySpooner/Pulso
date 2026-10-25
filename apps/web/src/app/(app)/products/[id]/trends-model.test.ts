import { describe, expect, test } from "vitest";

import { align, DAY, dayMs, gapBands, readState, windowDays, writeState, type Series } from "./trends-model";

const series = (days: string[], gaps: string[] = []): Series => ({
  metric: "price", unit: "usd_minor", source: "shopify_stores", source_name: "Shopify stores", method: null,
  as_of: "2026-10-24T06:00:00Z", stale: false,
  points: days.map((day, i) => ({ day, value: 2400 + i, high: 3900, as_of: `${day}T06:00:00Z` })),
  gaps: gaps.map((day) => ({ day, status: "gap" as const })),
});

describe("windowDays", () => {
  test("a range is the last n UTC days, today included", () => {
    expect(windowDays("7d", "2026-01-01", "2026-10-24")).toEqual(
      ["2026-10-18", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"],
    );
    expect(windowDays("30d", "2026-01-01", "2026-10-24")).toHaveLength(30);
    expect(windowDays("90d", "2026-10-20", "2026-10-24")[0]).toBe("2026-07-27"); // not clipped to the history
  });

  test("All starts on the real first day, across a month and a DST change (UTC days are 24 h)", () => {
    const days = windowDays("all", "2026-10-28", "2026-11-03");
    expect(days[0]).toBe("2026-10-28");
    expect(days.at(-1)).toBe("2026-11-03");
    expect(days).toHaveLength(7);
    expect(windowDays("all", "2026-10-24", "2026-10-24")).toEqual(["2026-10-24"]);
  });
});

describe("align", () => {
  test("a day without a point is null, never the neighbour's value", () => {
    const aligned = align(series(["2026-10-20", "2026-10-22"]), windowDays("7d", "", "2026-10-23"));
    expect(aligned.map((p) => p?.value ?? null)).toEqual([null, null, null, 2400, null, 2401, null]);
  });
});

describe("gapBands", () => {
  const days = windowDays("7d", "", "2026-10-24");

  test("consecutive gap days merge into one band covering whole UTC days", () => {
    const bands = gapBands([series([], ["2026-10-20", "2026-10-21", "2026-10-23"])], days);
    expect(bands).toEqual([
      { from: dayMs("2026-10-20"), to: dayMs("2026-10-22") },
      { from: dayMs("2026-10-23"), to: dayMs("2026-10-23") + DAY },
    ]);
  });

  test("gaps shared by a pane's series count once; gaps outside the window drop out; none gives none", () => {
    const bands = gapBands([series([], ["2026-10-01", "2026-10-21"]), series([], ["2026-10-21"])], days);
    expect(bands).toEqual([{ from: dayMs("2026-10-21"), to: dayMs("2026-10-22") }]);
    expect(gapBands([series(["2026-10-21"])], days)).toEqual([]);
  });
});

describe("URL state", () => {
  test("defaults read from a clean URL and leave it clean", () => {
    expect(readState(new URLSearchParams("tab=trends"))).toEqual({ range: "90d", overlay: null });
    expect(writeState("tab=trends", "90d", null, ["price", "stores"])).toBe("tab=trends");
    expect(writeState("tab=trends&range=7d", "90d", ["price", "stores"], ["price", "stores"])).toBe("tab=trends");
  });

  test("a range and a pane switched off round-trip; unknown values fall back", () => {
    const query = writeState("tab=trends&supplier=9", "7d", ["stores"], ["price", "stores"]);
    expect(query).toBe("tab=trends&supplier=9&range=7d&overlay=stores");
    expect(readState(new URLSearchParams(query))).toEqual({ range: "7d", overlay: ["stores"] });
    expect(readState(new URLSearchParams("range=14d&overlay=price,bogus"))).toEqual({ range: "90d", overlay: ["price"] });
    expect(readState(new URLSearchParams("overlay="))).toEqual({ range: "90d", overlay: [] });
  });
});
