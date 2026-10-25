import { describe, expect, it } from "vitest";

import { apiQuery, filterSearch, nextFilter, original, parseFilter, sparkSegments, stripScale, type Day } from "./model";

describe("sellers filter in the URL", () => {
  it("reads the chip, falling back to Active only", () => {
    expect(parseFilter(new URLSearchParams("tab=sellers&sellers=all"))).toBe("all");
    expect(parseFilter(new URLSearchParams("tab=sellers&sellers=tracked"))).toBe("tracked");
    expect(parseFilter(new URLSearchParams("sellers=active"))).toBe("active");
    expect(parseFilter(new URLSearchParams("sellers=bogus"))).toBe("active");
    expect(parseFilter(new URLSearchParams(""))).toBe("active");
  });

  it("writes the chip and keeps the tab; the default is never written", () => {
    expect(filterSearch("tab=sellers", "new")).toBe("tab=sellers&sellers=new");
    expect(filterSearch("tab=sellers&sellers=new", "active")).toBe("tab=sellers");
  });

  it("cycles in chip order and maps to the API", () => {
    expect([nextFilter("active"), nextFilter("all"), nextFilter("new"), nextFilter("tracked")]).toEqual(["all", "new", "tracked", "active"]);
    expect(apiQuery("active")).toEqual({});
    expect(apiQuery("all")).toEqual({ include_delisted: true });
    expect(apiQuery("new")).toEqual({ new_14d: true });
    expect(apiQuery("tracked")).toEqual({ tracked: true });
  });
});

describe("formatting and geometry", () => {
  it("formats the store's own currency at its exponent", () => {
    expect(original(4000, "CAD")).toBe("CA$40.00");
    expect(original(4000, "JPY")).toBe("¥4,000");
    expect(original(4000, "KWD")).toMatch(/^KWD\s4\.000$/); // Intl puts a no-break space after the code
  });

  it("places strip-plot dots and centres a single price", () => {
    expect(stripScale(null, null)).toBeNull();
    expect(stripScale(2000, 2000)!(2000)).toBe(0.5);
    const scale = stripScale(2000, 3000)!;
    expect([scale(2000), scale(2500), scale(3000)]).toEqual([0, 0.5, 1]);
  });

  it("breaks the sparkline at gap days and never bridges them", () => {
    const days: Day[] = [4, null, 2, 4, null].map((active, i) => ({ date: `2026-10-0${i + 1}`, active, gap: active === null, as_of: null }));
    expect(sparkSegments(days, 40, 10)).toEqual(["0.0,0.0", "20.0,5.0 30.0,0.0"]);
    expect(sparkSegments(days.map((d) => ({ ...d, active: null })), 40, 10)).toEqual([]);
  });
});
