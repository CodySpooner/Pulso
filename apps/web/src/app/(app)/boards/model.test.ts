import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { autosave, moved, moveOptions, type Item, type ItemPage, type SaveState } from "./model";

const item = (product_id: string, position: number): Item => ({ product_id, position, name: product_id, image_url: null, note: null, added_at: "2026-10-20T00:00:00Z" });
const ids = (items: Item[]) => items.map((i) => `${i.product_id}${i.position}`).join(" ");

describe("moved", () => {
  // Positions can have gaps after a removal (DEC-319 b); a move renumbers 0…n−1 like update_board_item.
  const page = [item("a", 0), item("b", 3), item("c", 4), item("d", 9)];

  test("moves a card down, up, to the end and past it, renumbering every card", () => {
    expect(ids(moved(page, "a", 2))).toBe("b0 c1 a2 d3");
    expect(ids(moved(page, "d", 0))).toBe("d0 a1 b2 c3");
    expect(ids(moved(page, "b", 3))).toBe("a0 c1 d2 b3");
    expect(ids(moved(page, "b", 99))).toBe("a0 c1 d2 b3");
  });

  test("an unknown card or its own place changes no order", () => {
    expect(moved(page, "zz", 1)).toBe(page);
    expect(ids(moved(page, "c", 2))).toBe("a0 b1 c2 d3");
  });
});

describe("moveOptions", () => {
  const KEY = ["get", "/v1/boards/{board_id}/items"];
  const setup = (send: () => Promise<Item>) => {
    const client = new QueryClient();
    client.setQueryData<ItemPage>(KEY, { items: [item("a", 0), item("b", 1), item("c", 2)], next_cursor: null });
    const observer = new MutationObserver(client, moveOptions(client, KEY, send));
    return { observer, order: () => client.getQueryData<ItemPage>(KEY)!.items.map((i) => i.product_id).join("") };
  };

  test("the card moves before the API answers", async () => {
    let answer!: (i: Item) => void;
    const { observer, order } = setup(() => new Promise((resolve) => (answer = resolve)));
    const done = observer.mutate({ product_id: "a", position: 2 });
    await vi.waitFor(() => expect(answer).toBeDefined());
    expect(order()).toBe("bca");
    answer(item("a", 2));
    await done;
    expect(order()).toBe("bca");
  });

  test("a failed save puts the order back", async () => {
    const { observer, order } = setup(() => Promise.reject(new Error("503")));
    await observer.mutate({ product_id: "c", position: 0 }).catch(() => {});
    expect(order()).toBe("abc");
  });
});

describe("autosave", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const setup = (fail: () => boolean = () => false) => {
    const sent: string[] = [];
    const states: SaveState[] = [];
    const answers: (() => void)[] = [];
    const save = (text: string) =>
      new Promise<void>((resolve, reject) => {
        sent.push(text);
        answers.push(() => (fail() ? reject(new Error("offline")) : resolve()));
      });
    const note = autosave(save, (s) => states.push(s), 800);
    const answer = async () => {
      answers.shift()!();
      await vi.advanceTimersByTimeAsync(0);
    };
    return { note, sent, states, answer };
  };

  test("typing waits for a pause and saves the last text once", async () => {
    const { note, sent, states, answer } = setup();
    note.change("Ord");
    await vi.advanceTimersByTimeAsync(500);
    note.change("Order 3");
    await vi.advanceTimersByTimeAsync(799);
    expect(sent).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(sent).toEqual(["Order 3"]);
    await answer();
    expect(states).toEqual(["pending", "pending", "saving", "saved"]);
  });

  test("a failed save keeps the text, and Retry sends it again", async () => {
    let offline = true;
    const { note, sent, states, answer } = setup(() => offline);
    note.change("Test with $50 cap");
    await vi.advanceTimersByTimeAsync(800);
    await answer();
    expect(states.at(-1)).toBe("error");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(sent).toHaveLength(1); // never retries on its own

    offline = false;
    note.flush(); // Retry
    await answer();
    expect(sent).toEqual(["Test with $50 cap", "Test with $50 cap"]);
    expect(states.at(-1)).toBe("saved");
  });

  test("typing after a failure saves the newer text", async () => {
    let offline = true;
    const { note, sent, states, answer } = setup(() => offline);
    note.change("first");
    await vi.advanceTimersByTimeAsync(800);
    await answer();
    offline = false;
    note.change("first, then more");
    await vi.advanceTimersByTimeAsync(800);
    await answer();
    expect(sent).toEqual(["first", "first, then more"]);
    expect(states.at(-1)).toBe("saved");
  });

  test("text typed during a save waits for it, then saves; never two saves at once", async () => {
    const { note, sent, states, answer } = setup();
    note.change("one");
    note.flush(); // blur saves at once
    expect(sent).toEqual(["one"]);
    note.change("one two");
    note.flush();
    expect(sent).toEqual(["one"]); // still in flight
    await answer();
    expect(sent).toEqual(["one", "one two"]);
    expect(states.at(-1)).toBe("saving");
    await answer();
    expect(states.at(-1)).toBe("saved");
  });

  test("a failure while newer text waits still saves the newer text", async () => {
    let offline = true;
    const { note, sent, states, answer } = setup(() => offline);
    note.change("old");
    note.flush();
    note.change("new");
    await answer(); // "old" fails while "new" waits
    offline = false;
    await vi.advanceTimersByTimeAsync(800);
    expect(sent).toEqual(["old", "new"]);
    await answer();
    expect(states.at(-1)).toBe("saved");
  });
});
