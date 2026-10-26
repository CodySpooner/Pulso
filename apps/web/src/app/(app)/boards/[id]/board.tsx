"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type Announcements, type UniqueIdentifier } from "@dnd-kit/core";
import { rectSortingStrategy, SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { Archive, ArchiveRestore, ArrowLeft, Bookmark, FlaskConical, LayoutGrid, Pencil, Rows3, SearchX, Trash2, X } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Ago, PanelError, Pill, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { isTyping } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, fetchClient, isProblem } from "@/lib/api/client";
import { duration, ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { reasonOf } from "../../testing/model";
import { boardsInit, boardsKey, itemsInit, itemsKey, moveOptions, type Board, type Item, type ItemPage, type Move } from "../model";
import { Segmented, Toast, useNote } from "../parts";
import { Card, Row, type CardProps } from "./cards";

const GRID = "grid gap-3 min-[480px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-4";
const plural = (n: number, one: string) => `${n.toLocaleString("en-US")} ${one}${n === 1 ? "" : "s"}`;
const LISTS = ["get", "/v1/boards"]; // both board lists (active and archived), never the cards

async function sendMove({ product_id, position }: Move, board_id: string) {
  const { data, error } = await fetchClient.PATCH("/v1/boards/{board_id}/items/{product_id}", { params: { path: { board_id, product_id } }, body: { position } });
  if (!data) throw error;
  return data;
}

// WF-3b (DEC-329): one board. The header edits in place; the cards show as a grid or a table (?view=table), reorder by
// drag or keyboard (dnd-kit sortable) through update_board_item, and take a note each that autosaves. A selection
// sends to Testing or removes, with Undo. There's no GET for one board, so it comes from the two board lists.
export function BoardView({ id }: { id: string }) {
  const client = useQueryClient();
  const ready = useApiReady();
  const active = $api.useQuery("get", "/v1/boards", boardsInit(false), { enabled: ready });
  const archived = $api.useQuery("get", "/v1/boards", boardsInit(true), { enabled: ready });
  const items = $api.useQuery("get", "/v1/boards/{board_id}/items", itemsInit(id), { enabled: ready });
  const board = active.data?.find((b) => b.id === id) ?? archived.data?.find((b) => b.id === id);
  const [note, setNote] = useNote();

  if (!board) {
    const gone = (active.data && archived.data) || (isProblem(items.error) && items.error.status === 404);
    const failed = active.isError ? active : archived.isError ? archived : null;
    if (gone)
      return (
        <EmptyState icon={SearchX} headingLevel="h1" title="Board not found" action={<Button asChild><Link href="/boards">All boards</Link></Button>}>
          It may have been deleted, or the link is wrong.
        </EmptyState>
      );
    if (failed)
      return (
        <div className="flex flex-col gap-5">
          <BackLink />
          <h1 className="text-title-1 font-semibold text-foreground">Board</h1>
          <section aria-label="Board" className="rounded-xl border border-border bg-card shadow-card">
            <PanelError title="Couldn't load this board" headingLevel="h2" size="md" error={failed.error} retry={() => void failed.refetch()} />
          </section>
        </div>
      );
    return <BoardSkeleton />;
  }

  // Every board write moves it up its list (DEC-319 d), so the lists refetch after each.
  const saved = (next?: Board) => {
    if (next) for (const a of [false, true]) client.setQueryData<Board[]>(boardsKey(a), (list) => list?.map((b) => (b.id === next.id ? next : b)));
    void client.invalidateQueries({ queryKey: LISTS });
  };
  const archive = async (on: boolean, undoable = true) => {
    const { data, error } = on
      ? await fetchClient.POST("/v1/boards/{board_id}/archive", { params: { path: { board_id: id } } })
      : await fetchClient.POST("/v1/boards/{board_id}/unarchive", { params: { path: { board_id: id } } });
    if (!data) return setNote({ tone: "error", text: `Couldn't ${on ? "archive" : "unarchive"} ${board.name}: ${reasonOf(error)}` });
    client.setQueryData<Board[]>(boardsKey(!on), (list) => list?.filter((b) => b.id !== id));
    client.setQueryData<Board[]>(boardsKey(on), (list) => list && [data, ...list.filter((b) => b.id !== id)]);
    saved();
    setNote({
      tone: "done",
      text: on ? `Archived ${data.name}. It's under Archived on your boards.` : `${data.name} is back on your boards.`,
      action: undoable && (
        <Button size="sm" variant="ghost" onClick={() => void archive(!on, false)}>
          Undo
        </Button>
      ),
    });
  };

  return (
    <div className="flex w-full flex-col gap-5">
      <Header board={board} now={active.dataUpdatedAt || archived.dataUpdatedAt} saved={saved} archive={archive} />
      <Cards board={board} setNote={setNote} saved={saved} />
      <Toast note={note} />
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/boards" className="flex w-fit items-center gap-1 rounded-sm text-label text-muted-foreground outline-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      <ArrowLeft className="size-3.5" aria-hidden />
      Boards
    </Link>
  );
}

function Header({ board, now, saved, archive }: { board: Board; now: number; saved: (b?: Board) => void; archive: (on: boolean) => Promise<void> }) {
  const patch = async (body: { name?: string; description?: string | null }) => {
    const { data, error } = await fetchClient.PATCH("/v1/boards/{board_id}", { params: { path: { board_id: board.id } }, body });
    if (!data) throw error;
    saved(data);
  };
  return (
    <header className="flex flex-col gap-3">
      <BackLink />
      {board.archived_at && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-secondary px-4 py-2.5 text-data text-muted-foreground">
          <Archive className="size-4 shrink-0" aria-hidden />
          <span className="flex-1">
            Archived <Ago iso={board.archived_at} now={now} source="Your board" />. It&apos;s hidden from your boards; its products and notes stay.
          </span>
          <Button size="sm" onClick={() => void archive(false)}>
            <ArchiveRestore aria-hidden />
            Unarchive
          </Button>
        </div>
      )}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Editable
            trigger="rename-board"
            label="Board name"
            value={board.name}
            maxLength={80}
            save={(name) => (name ? patch({ name }) : Promise.resolve())}
            problem={(e) => (isProblem(e) && e.status === 409 ? "You already have a board with that name. Archived boards count too." : null)}
            view={(edit) => (
              <h1 tabIndex={-1} className="group flex min-w-0 items-center gap-1.5 text-title-1 font-semibold text-foreground outline-none">
                <span onClick={edit} className="min-w-0 cursor-text break-words">
                  {board.name}
                </span>
                <Button id="rename-board" size="icon-sm" variant="ghost" aria-label="Rename board" onClick={edit} className="shrink-0">
                  <Pencil aria-hidden />
                </Button>
              </h1>
            )}
            inputClass="text-title-1 font-semibold"
          />
          <Editable
            trigger="edit-description"
            label="Description"
            value={board.description ?? ""}
            maxLength={10_000}
            multiline
            save={(text) => patch({ description: text || null })}
            view={(edit) => (
              <button id="edit-description" type="button" onClick={edit} className="w-fit max-w-[68ch] rounded-sm text-left text-body text-muted-foreground outline-none hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                {board.description || <span className="text-subtle-foreground">Add a description</span>}
                <span className="sr-only">, edit description</span>
              </button>
            )}
            inputClass="text-body"
          />
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-subtle-foreground">
            <span>
              <span className="font-mono tabular-nums">{board.item_count.toLocaleString("en-US")}</span> {board.item_count === 1 ? "product" : "products"}
            </span>
            <span aria-hidden>·</span>
            <span>
              Updated <Ago iso={board.updated_at} now={now} source="Your board's last change" />
            </span>
            {board.archived_at && (
              <Pill tone="neutral" icon={Archive}>
                Archived
              </Pill>
            )}
          </p>
        </div>
        {!board.archived_at && (
          <Button onClick={() => void archive(true)} className="self-start">
            <Archive aria-hidden />
            Archive
          </Button>
        )}
      </div>
    </header>
  );
}

/** Text that edits in place: Enter (or leaving the field) saves, Escape cancels, a blank name keeps the old one.
 *  A refused save keeps the field open with the text and the reason; focus returns where editing began. */
function Editable({
  label,
  value,
  maxLength,
  multiline,
  save,
  problem,
  view,
  inputClass,
  trigger,
}: {
  trigger: string;
  label: string;
  value: string;
  maxLength: number;
  multiline?: boolean;
  save: (text: string) => Promise<void>;
  problem?: (error: unknown) => string | null;
  view: (edit: () => void) => React.ReactNode;
  inputClass: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const close = () => {
    setDraft(null);
    setError(null);
    requestAnimationFrame(() => document.getElementById(trigger)?.focus()); // the trigger remounts with the text
  };
  const commit = async () => {
    if (draft === null || busy) return;
    const text = draft.trim();
    if (text === value) return close();
    setBusy(true);
    try {
      await save(text);
      close();
    } catch (e) {
      setError(problem?.(e) ?? `Couldn't save: ${reasonOf(e)}`);
    } finally {
      setBusy(false);
    }
  };
  if (draft === null) return view(() => setDraft(value));
  const Field = multiline ? "textarea" : "input";
  return (
    <div className="flex flex-col gap-1">
      <Field
        autoFocus
        aria-label={label}
        value={draft}
        maxLength={maxLength}
        rows={multiline ? 2 : undefined}
        aria-invalid={!!error}
        aria-describedby={error ? `${label}-error` : undefined}
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => (setDraft(e.target.value), setError(null))}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === "Escape") close();
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void commit();
          }
        }}
        className={cn(
          "-mx-2 field-sizing-content min-w-0 resize-none rounded-md border border-input bg-background px-2 py-0.5 text-foreground outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring aria-invalid:border-negative",
          inputClass,
        )}
      />
      {error ? (
        <p id={`${label}-error`} role="alert" className="text-label text-negative">
          {error}
        </p>
      ) : (
        <p className="text-label text-subtle-foreground max-sm:hidden">{busy ? "Saving…" : `Enter to save · Esc to cancel${multiline ? " · Shift+Enter for a new line" : ""}`}</p>
      )}
    </div>
  );
}

function Cards({ board, setNote, saved }: { board: Board; setNote: ReturnType<typeof useNote>[1]; saved: (b?: Board) => void }) {
  const client = useQueryClient();
  const id = board.id;
  const items = $api.useQuery("get", "/v1/boards/{board_id}/items", itemsInit(id), { enabled: useApiReady() }); // BoardView's query, shared
  const key = itemsKey(id);
  const view = useSearchParams().get("view") === "table" ? "table" : "grid";
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const anchor = useRef<string | null>(null);
  const lifted = useRef(false); // dnd-kit reports the card over itself on pick-up; that one isn't a move
  const move = useMutation(moveOptions(client, key, (m) => sendMove(m, id)));
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  if (!items.data)
    return items.isError ? (
      <section aria-label="Products" className="rounded-xl border border-border bg-card shadow-card">
        <PanelError title="Couldn't load this board's products" headingLevel="h2" size="md" error={items.error} retry={() => void items.refetch()} />
      </section>
    ) : (
      <CardsSkeleton />
    );

  const cards = items.data.items;
  const ids = cards.map((c) => c.product_id);
  const chosen = cards.filter((c) => selected.has(c.product_id));
  const name = (pid: UniqueIdentifier) => cards.find((c) => c.product_id === pid)?.name ?? "The product";
  const place = (pid: UniqueIdentifier) => ids.indexOf(String(pid)) + 1;
  const announcements: Announcements = {
    onDragStart: ({ active }) => ((lifted.current = true), `Picked up ${name(active.id)}, position ${place(active.id)} of ${ids.length}.`),
    onDragOver: ({ active, over }) => {
      if (lifted.current && over?.id === active.id) return (lifted.current = false), undefined;
      lifted.current = false;
      return over ? `${name(active.id)} is at position ${place(over.id)} of ${ids.length}.` : `${name(active.id)} is outside the board.`;
    },
    onDragEnd: ({ active, over }) => (over ? `Dropped ${name(active.id)} at position ${place(over.id)} of ${ids.length}.` : `Dropped ${name(active.id)}. The order didn't change.`),
    onDragCancel: ({ active }) => `Cancelled. ${name(active.id)} is back at position ${place(active.id)}.`,
  };

  const reorder = (product_id: string, to: number) => {
    if (to === ids.indexOf(product_id)) return;
    move.mutate(
      { product_id, position: to },
      {
        onSuccess: () => saved(),
        onError: (error) => setNote({ tone: "error", text: `Couldn't save the order: ${reasonOf(error)} Reverted.` }),
      },
    );
  };
  const saveNote = (product_id: string) => async (note: string | null) => {
    const { data, error } = await fetchClient.PATCH("/v1/boards/{board_id}/items/{product_id}", { params: { path: { board_id: id, product_id } }, body: { note } });
    if (!data) throw error;
    client.setQueryData<ItemPage>(key, (page) => page && { ...page, items: page.items.map((c) => (c.product_id === product_id ? { ...c, note: data.note } : c)) });
    saved();
  };
  const select = (pid: string, shift: boolean) => {
    const from = anchor.current ? ids.indexOf(anchor.current) : -1;
    setSelected((was) => {
      const next = new Set(was);
      if (shift && from >= 0) {
        const to = ids.indexOf(pid);
        for (const each of ids.slice(Math.min(from, to), Math.max(from, to) + 1)) next.add(each);
      } else if (!next.delete(pid)) next.add(pid);
      return next;
    });
    anchor.current = pid;
  };

  // Removal is optimistic; Undo adds the cards back and puts each at its old place with its note.
  const remove = async (gone: Item[]) => {
    const at = gone.map((c) => ({ ...c, index: ids.indexOf(c.product_id) })).sort((a, b) => a.index - b.index);
    const before = items.data;
    const off = new Set(at.map((c) => c.product_id));
    setSelected(new Set());
    client.setQueryData<ItemPage>(key, (page) => page && { ...page, items: page.items.filter((c) => !off.has(c.product_id)) });
    const results = await Promise.all(gone.map((c) => fetchClient.DELETE("/v1/boards/{board_id}/items/{product_id}", { params: { path: { board_id: id, product_id: c.product_id } } })));
    const failed = results.find((r) => !r.data);
    void client.invalidateQueries({ queryKey: key });
    saved();
    if (failed) {
      client.setQueryData(key, before);
      return setNote({ tone: "error", text: `Couldn't remove ${gone.length === 1 ? gone[0].name : plural(gone.length, "product")}: ${reasonOf(failed.error)}` });
    }
    const restore = async () => {
      setNote(null);
      const added = await fetchClient.POST("/v1/boards/{board_id}/items", { params: { path: { board_id: id } }, body: { product_ids: at.map((c) => c.product_id) } });
      for (const c of added.data ? at : []) await fetchClient.PATCH("/v1/boards/{board_id}/items/{product_id}", { params: { path: { board_id: id, product_id: c.product_id } }, body: { position: c.index, note: c.note } });
      void client.invalidateQueries({ queryKey: key });
      saved();
      if (!added.data) setNote({ tone: "error", text: `Couldn't put them back: ${reasonOf(added.error)}` });
    };
    setNote({
      tone: "done",
      text: `Removed ${gone.length === 1 ? gone[0].name : plural(gone.length, "product")} from ${board.name}.`,
      action: (
        <Button size="sm" variant="ghost" onClick={() => void restore()}>
          Undo
        </Button>
      ),
    });
  };
  const sendToTesting = async () => {
    const { data, error } = await fetchClient.POST("/v1/boards/{board_id}/items/send-to-testing", { params: { path: { board_id: id } }, body: { product_ids: chosen.map((c) => c.product_id) } });
    saved();
    if (!data) return setNote({ tone: "error", text: `Couldn't send to Testing: ${reasonOf(error)}` });
    setSelected(new Set());
    const open = data.skipped.map(name);
    setNote({
      tone: "done",
      text: [data.created.length ? `Sent ${plural(data.created.length, "product")} to Testing as ideas.` : "Nothing new sent to Testing.", open.length ? `Already testing: ${open.join(", ")}.` : ""].join(" ").trim(),
      action: (
        <Button asChild size="sm" variant="ghost">
          <Link href="/testing">Open Testing</Link>
        </Button>
      ),
    });
  };

  const setView = (next: "grid" | "table") => {
    const params = new URLSearchParams(window.location.search);
    if (next === "table") params.set("view", "table");
    else params.delete("view");
    window.history.replaceState(null, "", params.size ? `?${params}` : window.location.pathname);
  };
  const props = (item: Item, index: number): CardProps => ({
    item,
    index,
    count: cards.length,
    now: items.dataUpdatedAt,
    selected: selected.has(item.product_id),
    onSelect: (shift) => select(item.product_id, shift),
    onMove: (to) => reorder(item.product_id, to),
    onRemove: () => void remove([item]),
    saveNote: saveNote(item.product_id),
  });

  return (
    <section
      aria-label="Products"
      className="flex flex-col gap-3"
      onKeyDown={(e) => {
        if (isTyping(e.target) && !(e.target instanceof HTMLInputElement && e.target.type === "checkbox")) return;
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
          e.preventDefault();
          setSelected(new Set(ids));
          // A lifted card's handle is aria-pressed: its Escape cancels the drag and keeps the selection.
        } else if (e.key === "Escape" && selected.size && !(e.target instanceof HTMLElement && e.target.getAttribute("aria-pressed") === "true")) setSelected(new Set());
      }}
    >
      {items.isRefetchError && <StaleLine boxed what="Couldn't refresh this board" error={items.error} asOf={items.dataUpdatedAt} retry={() => void items.refetch()} />}
      {cards.length === 0 ? (
        <div className="rounded-xl border border-border bg-card shadow-card">
          <EmptyState
            icon={Bookmark}
            headingLevel="h2"
            title="No products on this board yet"
            action={
              <Button asChild>
                <Link href="/discover">Browse Discover</Link>
              </Button>
            }
          >
            Products you add from Discover or a product page land here in the order you add them. The Add to board button comes in a later Phase 4 update.
          </EmptyState>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Segmented
              id="board-view"
              label="View"
              value={view}
              options={[
                { value: "grid", label: "Grid", icon: LayoutGrid },
                { value: "table", label: "Table", icon: Rows3 },
              ]}
              onChange={setView}
            />
            <p className="text-label text-subtle-foreground max-md:hidden">Drag a product by its handle, or focus the handle and use Space and the arrow keys.</p>
          </div>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            accessibility={{ announcements, screenReaderInstructions: { draggable: "To move this product, press Space or Enter. Move it with the arrow keys, then press Space or Enter to drop it, or Escape to cancel." } }}
            onDragEnd={({ active, over }) => over && reorder(String(active.id), ids.indexOf(String(over.id)))}
          >
            <SortableContext items={ids} strategy={view === "grid" ? rectSortingStrategy : verticalListSortingStrategy}>
              {view === "grid" ? (
                <ul aria-label={`${board.name}, in your order`} className={GRID}>
                  {cards.map((item, i) => (
                    <Card key={item.product_id} {...props(item, i)} />
                  ))}
                </ul>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-card">
                  <table className="w-full border-collapse text-data">
                    <caption className="sr-only">{board.name}, in your order</caption>
                    <thead className="sticky top-0 z-20 bg-card text-label text-subtle-foreground">
                      <tr className="border-b border-border">
                        <th scope="col" className="py-2 pl-3 font-medium">
                          <span className="sr-only">Selected</span>
                        </th>
                        <th scope="col" className="py-2 font-medium">
                          <span className="sr-only">Reorder</span>
                        </th>
                        <th scope="col" className="py-2 pr-2 text-right font-medium">
                          #
                        </th>
                        <th scope="col" className="py-2 pr-4 text-left font-medium">
                          Product
                        </th>
                        {["Price", "Best margin", "Trend"].map((label) => (
                          <th key={label} scope="col" className="py-2 pr-3 text-right font-medium whitespace-nowrap">
                            {label}
                          </th>
                        ))}
                        <th scope="col" className="py-2 pr-3 text-left font-medium">
                          Lifecycle
                        </th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">
                          Saturation
                        </th>
                        <th scope="col" className="py-2 pr-4 text-left font-medium">
                          Note
                        </th>
                        <th scope="col" className="py-2 pr-3 text-left font-medium whitespace-nowrap">
                          Data as of
                        </th>
                        <th scope="col" className="py-2 pr-2 text-right font-medium">
                          Added
                        </th>
                        <th scope="col" className="py-2 pr-3">
                          <span className="sr-only">Actions</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {cards.map((item, i) => (
                        <Row key={item.product_id} {...props(item, i)} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SortableContext>
          </DndContext>
          {items.data.next_cursor != null && <p className="text-label text-subtle-foreground">Showing the first 100 products on this board.</p>}
        </>
      )}
      <SelectionBar count={chosen.length} onSend={() => void sendToTesting()} onRemove={() => void remove(chosen)} onClear={() => setSelected(new Set())} />
    </section>
  );
}

/** The bulk actions for the selected cards; it rides at the bottom of the screen while a selection exists. */
function SelectionBar({ count, onSend, onRemove, onClear }: { count: number; onSend: () => void; onRemove: () => void; onClear: () => void }) {
  return (
    <div className="pointer-events-none sticky bottom-20 z-30 flex justify-center lg:bottom-6">
      <AnimatePresence>
        {count > 0 && (
          <m.div
            role="toolbar"
            aria-label="Selected products"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8, transition: { duration: duration.fast } }}
            transition={{ duration: duration.base, ease: ease.out }}
            className="pointer-events-auto flex flex-wrap items-center gap-1 rounded-xl border border-border bg-popover p-1.5 pl-3 text-popover-foreground shadow-dialog"
          >
            <span className="mr-2 text-data font-medium tabular-nums">{count} selected</span>
            <Button size="sm" variant="primary" onClick={onSend}>
              <FlaskConical aria-hidden />
              Send to Testing
            </Button>
            <Button size="sm" variant="ghost" onClick={onRemove}>
              <Trash2 aria-hidden />
              Remove
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label="Clear selection" onClick={onClear}>
              <X aria-hidden />
            </Button>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CardsSkeleton() {
  return (
    <div role="status" aria-label="Loading this board's products" className={GRID}>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="overflow-hidden rounded-xl border border-border bg-card">
          <Skeleton className="aspect-[4/3] w-full rounded-none" />
          <div className="flex flex-col gap-2 p-3">
            <Skeleton className="h-4 w-3/4" />
            <div className="flex flex-col gap-2 border-t border-border-subtle pt-2">
              {[0, 1, 2, 3, 4].map((row) => (
                <Skeleton key={row} className="h-3.5" />
              ))}
            </div>
            <Skeleton className="h-8" />
            <Skeleton className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function BoardSkeleton() {
  return (
    <div role="status" aria-label="Loading the board" className="flex w-full flex-col gap-5">
      <div className="flex flex-col gap-3">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-80 max-w-full" />
        <Skeleton className="h-3 w-40" />
      </div>
      <CardsSkeleton />
    </div>
  );
}
