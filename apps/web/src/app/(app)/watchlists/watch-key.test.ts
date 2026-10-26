import { describe, expect, test } from "vitest";

import { starFor, type KeyInput } from "./watch-key";

// Duck-typed stand-ins for the DOM: Vitest runs in Node.
const star = { id: "star" } as unknown as HTMLElement;
const pageStar = { id: "page star" } as unknown as HTMLElement;
const box = (attr: "data-product" | "role", holds: HTMLElement | null) => ({
  hasAttribute: (name: string) => name === attr,
  querySelector: (selector: string) => (selector === "[data-star]" ? holds : null),
});
const el = (tagName: string, inside: ReturnType<typeof box> | null = null, isContentEditable = false) =>
  ({ tagName, isContentEditable, closest: () => inside }) as unknown as EventTarget;
const page = (holds: HTMLElement | null) => ({ querySelector: (selector: string) => (selector === '[data-star="page"]' ? holds : null) }) as ParentNode;
const card = box("data-product", star);
const press = (target: EventTarget | null, over: Partial<KeyInput> = {}, on = page(null)) =>
  starFor({ key: "w", ctrlKey: false, metaKey: false, altKey: false, repeat: false, target, ...over }, on);

describe("W, the ★ key", () => {
  test("toggles the ★ on the focused product, either case", () => {
    expect(press(el("A", card))).toBe(star);
    expect(press(el("BUTTON", card), { key: "W" })).toBe(star);
  });

  test("outside any product, only a page that is one product has a ★ to toggle", () => {
    expect(press(el("BODY"), {}, page(pageStar))).toBe(pageStar);
    expect(press(el("BODY"))).toBeNull(); // Discover with no card focused
    expect(press(null, {}, page(pageStar))).toBe(pageStar);
  });

  test("a product without a ★ does nothing, even on a page that has one", () => {
    expect(press(el("A", box("data-product", null)), {}, page(pageStar))).toBeNull();
  });

  test("never while typing in a field", () => {
    for (const tagName of ["INPUT", "TEXTAREA", "SELECT"]) expect(press(el(tagName, card))).toBeNull();
    expect(press(el("DIV", card, true))).toBeNull();
  });

  test("never with Ctrl, ⌘ or Alt, held down, or for another key", () => {
    for (const over of [{ ctrlKey: true }, { metaKey: true }, { altKey: true }, { repeat: true }, { key: "b" }]) expect(press(el("A", card), over)).toBeNull();
  });

  test("never in a dialog or menu, whose letters are its own (typeahead)", () => {
    expect(press(el("DIV", box("role", star)), {}, page(pageStar))).toBeNull();
  });
});
