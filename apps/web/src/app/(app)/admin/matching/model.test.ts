import { describe, expect, test } from "vitest";

import { keyAction, mergeDirection, money, nextAfter, step, type Cluster, type KeyInput } from "./model";

const press = (key: string, over: Partial<KeyInput> = {}) =>
  keyAction({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, target: null, ...over });

describe("keyboard map", () => {
  test("one key per decision and move, either case", () => {
    expect(["a", "R", "s", "m", "x", "u", "j", "K"].map((key) => press(key)?.type)).toEqual([
      "accept",
      "reject",
      "skip",
      "merge",
      "split",
      "undo",
      "next",
      "prev",
    ]);
  });

  test("1–4 pick a gallery image; 0 and 5 do nothing", () => {
    expect(["1", "2", "3", "4"].map((key) => press(key))).toEqual([0, 1, 2, 3].map((index) => ({ type: "image", index })));
    expect(press("0")).toBeNull();
    expect(press("5")).toBeNull();
  });

  test("Ctrl+Z and ⌘+Z undo; other modified keys are the browser's", () => {
    expect(press("z", { ctrlKey: true })).toEqual({ type: "undo" });
    expect(press("Z", { metaKey: true })).toEqual({ type: "undo" });
    expect(press("z", { ctrlKey: true, shiftKey: true })).toBeNull(); // redo
    expect(press("a", { ctrlKey: true })).toBeNull(); // select all
    expect(press("r", { metaKey: true })).toBeNull(); // reload
    expect(press("a", { altKey: true })).toBeNull();
    expect(press("A", { shiftKey: true })).toBeNull(); // batch accept is a backlog row
    expect(press("z")).toBeNull();
  });

  test("a held key repeats moves, never decisions", () => {
    for (const key of ["a", "r", "m", "x", "u"]) expect(press(key, { repeat: true })).toBeNull();
    expect(press("z", { ctrlKey: true, repeat: true })).toBeNull();
    expect(["j", "k", "s"].map((key) => press(key, { repeat: true })?.type)).toEqual(["next", "prev", "skip"]);
  });

  test("typing in a field is never a shortcut", () => {
    for (const tagName of ["INPUT", "TEXTAREA", "SELECT"]) expect(press("a", { target: { tagName } as unknown as EventTarget })).toBeNull();
    expect(press("a", { target: { tagName: "DIV", isContentEditable: true } as unknown as EventTarget })).toBeNull();
    expect(press("a", { target: { tagName: "BUTTON" } as unknown as EventTarget })).toEqual({ type: "accept" });
  });
});

describe("queue moves", () => {
  test("after a decision the next pair shows, else the one before, else none", () => {
    expect(nextAfter([1, 2, 3], 2)).toBe(3);
    expect(nextAfter([1, 2, 3], 3)).toBe(2);
    expect(nextAfter([3], 3)).toBeNull();
    expect(nextAfter([4, 5], 9)).toBe(4); // gone already: the first
  });

  test("J and K step one and stop at the ends", () => {
    expect(step([1, 2, 3], 1, 1)).toBe(2);
    expect(step([1, 2, 3], 3, 1)).toBe(3);
    expect(step([1, 2, 3], 1, -1)).toBe(1);
    expect(step([1, 2, 3], null, 1)).toBe(1);
    expect(step([], 1, 1)).toBeNull();
  });
});

describe("merge and money", () => {
  const cluster = (id: string, first_seen_at: string): Cluster => ({ product_id: id, name: id, first_seen_at, listings: 1, members: [], notes: 0, tags: 0 });

  test("the younger product merges into the older, as accept does", () => {
    const older = cluster("b", "2026-10-01T00:00:00Z");
    const younger = cluster("a", "2026-10-09T00:00:00Z");
    expect(mergeDirection([younger, older])).toEqual({ from: younger, into: older });
    const tie = cluster("c", "2026-10-01T00:00:00Z");
    expect(mergeDirection([tie, older])).toEqual({ from: tie, into: older }); // then by id
    expect(mergeDirection([older])).toBeNull();
  });

  test("prices read in their own currency's minor units", () => {
    expect(money(1999, "USD")).toBe("$19.99");
    expect(money(1500, "JPY")).toBe("¥1,500");
    expect(money(12345, "KWD")).toBe("KWD 12.345"); // a no-break space
  });
});
