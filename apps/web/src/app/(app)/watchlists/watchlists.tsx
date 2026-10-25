"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { GitMerge, ListPlus, MoreHorizontal, Plus, Star } from "lucide-react";
import { DropdownMenu } from "radix-ui";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, Pill, StaleLine } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { EmptyState } from "@/components/pulso/empty-state";
import { Metric } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, fetchClient, isProblem } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { duration, ease, spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { BestMargin, count, day, Freshness, Price, Thumb, Velocity } from "../discover/feed-views";
import { isMerged, pickList, refreshWatchlists, undoWindow, type List, type Removal, type Row } from "./model";

interface Note {
  text: string;
  undo?: () => void;
}
const NO_PAUSE = new Map<string, string>(); // the items page names no degraded source; each row's dot shows staleness
const reason = (error: unknown) => (isProblem(error) ? error.detail : "The Pulso API didn't answer. Check that it is running, then try again.");
const card = "rounded-xl border border-border bg-card shadow-card";
const menu =
  "z-50 max-h-80 min-w-48 overflow-y-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)";
const menuItem = "flex h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-data outline-none select-none pointer-coarse:h-(--hit-target) data-highlighted:bg-accent";
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";
// imp-419 adds the 30-day sparkline after Velocity; nothing stands in for it until then.
const COLUMNS = ["Product", "Price", "Velocity", "Best margin", "Stores", "Added", "Last seen"];
// Selected: brand over the card, opaque like --table-row-hover, so the sticky product cell matches its row.
const PICKED = "bg-[color-mix(in_oklab,var(--brand)_10%,var(--card))]";

// WF-2b (vault Features/Watchlists, DEC-322): the lists, and the list in the URL (?list=) as a dense table, cards on a
// phone. Removal hides at once and is sent after the 5-second undo; a move is sent at once.
export function Watchlists() {
  const lists = $api.useQuery("get", "/v1/watchlists", {}, { enabled: useApiReady() });
  const current = pickList(lists.data, useSearchParams().get("list"));
  const [dialog, setDialog] = useState<"create" | "rename" | "delete" | null>(null);
  const select = (id: string) => window.history.replaceState(null, "", `?list=${id}`);

  if (!lists.data)
    return lists.isError ? (
      <section className={card}>
        <PanelError headingLevel="h2" size="md" title="Couldn't load your watchlists" error={lists.error} retry={() => void lists.refetch()} />
      </section>
    ) : (
      <PageSkeleton />
    );
  const dialogs = (
    <>
      <NameDialog open={dialog === "create" || dialog === "rename"} list={dialog === "rename" ? current : undefined} onClose={() => setDialog(null)} onSaved={select} />
      <DeleteDialog list={dialog === "delete" ? current : undefined} onClose={() => setDialog(null)} />
    </>
  );
  if (!current)
    return (
      <section className={card}>
        <EmptyState
          icon={Star}
          headingLevel="h2"
          title="Star products to watch them here"
          action={
            <>
              <Button asChild variant="secondary">
                <Link href="/discover">Find products in Discover</Link>
              </Button>
              <Button variant="ghost" onClick={() => setDialog("create")}>
                <Plus aria-hidden />
                New list
              </Button>
            </>
          }
        >
          Press ★ on a product in Discover or on its page. Starred products land in Main, with their price, velocity and margin kept up to date here.
        </EmptyState>
        {dialogs}
      </section>
    );
  return (
    <div className="grid items-start gap-4 md:grid-cols-[12rem_minmax(0,1fr)]">
      {lists.isRefetchError && <StaleLine boxed className="md:col-span-2" what="Couldn't refresh your lists" error={lists.error} asOf={lists.dataUpdatedAt} retry={() => void lists.refetch()} />}
      <nav aria-label="Watchlists" className="max-md:hidden">
        <ul className="flex flex-col gap-0.5">
          {lists.data.map((l) => (
            <li key={l.id}>
              <button
                type="button"
                aria-current={l.id === current.id ? "page" : undefined}
                onClick={() => select(l.id)}
                className={cn(
                  "relative flex h-8 w-full items-center gap-2 rounded-md px-2.5 text-left text-data transition-colors duration-(--duration-fast)",
                  l.id === current.id ? "text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {l.id === current.id && <m.span layoutId="watchlist-active" transition={spring.snappy} className="absolute inset-0 rounded-md bg-accent" />}
                <span className="relative min-w-0 flex-1 truncate font-medium">{l.name}</span>
                <span className="relative font-mono text-label text-subtle-foreground tabular-nums">{l.item_count}</span>
              </button>
            </li>
          ))}
        </ul>
        <Button variant="ghost" size="sm" className="mt-2 w-full justify-start" onClick={() => setDialog("create")}>
          <Plus aria-hidden />
          New list
        </Button>
      </nav>
      {/* A phone switches lists from a dropdown above the cards. */}
      <div className="flex gap-2 md:hidden">
        <select
          aria-label="Watchlist"
          value={current.id}
          onChange={(e) => select(e.target.value)}
          className="h-(--button-h-md) min-w-0 flex-1 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground"
        >
          {lists.data.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name} ({l.item_count})
            </option>
          ))}
        </select>
        <Button aria-label="New list" size="icon" className="size-(--button-h-md)" onClick={() => setDialog("create")}>
          <Plus aria-hidden />
        </Button>
      </div>
      <ListPanel key={current.id} list={current} lists={lists.data} onSettings={setDialog} />
      {dialogs}
    </div>
  );
}

function ListPanel({ list, lists, onSettings }: { list: List; lists: List[]; onSettings: (d: "rename" | "delete") => void }) {
  const client = useQueryClient();
  const items = $api.useInfiniteQuery(
    "get",
    "/v1/watchlists/{watchlist_id}/items",
    { params: { path: { watchlist_id: list.id }, query: { limit: 100 } } },
    { pageParamName: "cursor", initialPageParam: null, getNextPageParam: (page) => page.next_cursor },
  );
  const [gone, setGone] = useState<ReadonlySet<string>>(new Set()); // removed or moved, until the list refetches
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [note, setNote] = useState<Note | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const hide = (ids: string[], on: boolean) => setGone((g) => new Set(on ? [...g, ...ids] : [...g].filter((id) => !ids.includes(id))));
  const settle = async (ids: string[]) => {
    await refreshWatchlists(client, true);
    hide(ids, false);
  };

  // The panel is keyed by its list, so this first render's list id, client and setters hold for its life.
  const [removals] = useState(() =>
    undoWindow(
      ({ ids }: Removal) =>
        // ponytail: one DELETE per item (there's no bulk remove); a list stays under 200 rows.
        void Promise.all(ids.map((product_id) => fetchClient.DELETE("/v1/watchlists/{watchlist_id}/items/{product_id}", { params: { path: { watchlist_id: list.id, product_id } } })))
          .then((answers) => answers.find((a) => a.error !== undefined)?.error, (error: unknown) => error ?? null)
          .then((error) => {
            if (error !== undefined) setNote({ text: `Couldn't remove from ${list.name}: ${reason(error)} The products are back.` });
            return settle(ids);
          }),
      () => {},
    ),
  );
  useEffect(() => () => removals.flush(), [removals]); // leaving the list sends what's pending

  const rows: Row[] = (items.data?.pages.flatMap((p) => p.items) ?? []).filter((r) => !gone.has(r.product_id));
  const pick = [...selected].filter((id) => rows.some((r) => r.product_id === id));
  const focusAfter = (ids: string[]) => {
    const at = rows.findIndex((r) => ids.includes(r.product_id));
    const next = rows.slice(at).find((r) => !ids.includes(r.product_id)) ?? rows.slice(0, at).findLast((r) => !ids.includes(r.product_id));
    // The table and the cards both render; only one is shown.
    const links = next ? [...document.querySelectorAll<HTMLElement>(`[data-row="${next.product_id}"] a`)] : [];
    requestAnimationFrame(() => (links.find((a) => a.offsetParent !== null) ?? heading.current)?.focus());
  };
  const remove = (ids: string[], title: string) => {
    const text = ids.length === 1 ? `Removed ${title} from ${list.name}.` : `Removed ${ids.length} products from ${list.name}.`;
    focusAfter(ids);
    hide(ids, true);
    setSelected(new Set());
    removals.remove({ list: list.id, ids, text });
    const undo = () => {
      removals.undo();
      hide(ids, false);
      setNote(null);
    };
    setNote({ text, undo });
  };
  const move = useMutation({
    mutationFn: async ({ ids, to }: { ids: string[]; to: List }) => {
      const { error } = await fetchClient.POST("/v1/watchlists/{watchlist_id}/items/move", { params: { path: { watchlist_id: list.id } }, body: { product_ids: ids, to: to.id } });
      if (error !== undefined) throw error;
    },
    onMutate: ({ ids }) => {
      focusAfter(ids);
      hide(ids, true);
      setSelected(new Set());
    },
    onSuccess: (_, { ids, to }) => setNote({ text: ids.length === 1 ? `Moved to ${to.name}.` : `Moved ${ids.length} products to ${to.name}.` }),
    onError: (error, { to }) => setNote({ text: `Couldn't move to ${to.name}: ${reason(error)}` }),
    onSettled: (_, __, { ids }) => settle(ids),
  });
  const actions = { lists: lists.filter((l) => l.id !== list.id), move: (ids: string[], to: List) => move.mutate({ ids, to }), remove };

  // Ctrl+Z (⌘Z) undoes while the toast offers it (vault UX spec, Keyboard).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (note?.undo && e.key.toLowerCase() === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
        e.preventDefault();
        note.undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [note]);
  useEffect(() => {
    if (!note) return;
    const timer = setTimeout(() => setNote(null), note.undo ? 5000 : 6000);
    return () => clearTimeout(timer);
  }, [note]);

  const now = items.dataUpdatedAt;
  const shown = Math.max(0, list.item_count - gone.size); // what's hidden meanwhile was all on this list
  const all = rows.length > 0 && pick.length === rows.length;
  return (
    <section aria-labelledby="watchlist-title" className="flex min-w-0 flex-col gap-3">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 ref={heading} id="watchlist-title" tabIndex={-1} className="min-w-0 truncate text-title-3 font-semibold text-foreground outline-none">
          {list.name}
        </h2>
        <p className="text-label text-subtle-foreground tabular-nums">
          {count(shown)} {shown === 1 ? "product" : "products"}
        </p>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label={`${list.name} settings`} className="ml-auto">
              <MoreHorizontal aria-hidden />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={4} className={menu}>
              <DropdownMenu.Item className={menuItem} onSelect={() => onSettings("rename")}>
                Rename…
              </DropdownMenu.Item>
              <DropdownMenu.Item className={cn(menuItem, "text-negative")} onSelect={() => onSettings("delete")}>
                Delete list…
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </header>
      {pick.length > 0 && (
        <div role="toolbar" aria-label="Selected products" className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-2">
          <span className="mr-auto text-data font-medium text-foreground tabular-nums">{pick.length} selected</span>
          <MoveMenu label="Move to…" lists={actions.lists} onMove={(to) => actions.move(pick, to)} />
          <Button size="sm" onClick={() => remove(pick, rows.find((r) => r.product_id === pick[0])!.product.title)}>
            Remove
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
            Clear selection
          </Button>
        </div>
      )}
      {items.data && items.isRefetchError && <StaleLine boxed what="Couldn't refresh this list" error={items.error} asOf={now} retry={() => void items.refetch()} />}
      {!items.data ? (
        items.isError ? (
          <section className={card}>
            <PanelError headingLevel="h3" title="Couldn't load this list" error={items.error} retry={() => void items.refetch()} />
          </section>
        ) : (
          <TableSkeleton />
        )
      ) : rows.length === 0 && !items.hasNextPage ? (
        <section className={card}>
          <EmptyState
            icon={list.name === "Main" ? Star : ListPlus}
            headingLevel="h3"
            title={list.name === "Main" ? "Star products to watch them here" : "This list is empty"}
            action={
              <Button asChild variant="secondary">
                <Link href="/discover">Find products in Discover</Link>
              </Button>
            }
          >
            {list.name === "Main" ? "Press ★ on a product in Discover or on its page and it lands here." : "Move products here from Main with a row's menu, or tick the lists a product is on from its page."}
          </EmptyState>
        </section>
      ) : (
        // A CSS fade: one held by Motion stays at opacity 0 until LazyMotion's features load after a full page load.
        <div className="flex flex-col gap-3 animate-in fade-in-0 duration-(--duration-fast)">
          {/* Lists stay well under 200 rows and aren't virtualized, so a removed row may fade out (Motion System). */}
          <div role="region" aria-label={`${list.name} products`} tabIndex={0} className={cn(card, "max-h-[max(24rem,calc(100dvh-15rem))] overflow-auto overscroll-contain max-md:hidden")}>
            <table className="w-full min-w-200 border-separate border-spacing-0 zone-data">
              <thead className="sticky top-0 z-20 bg-card">
                <tr className="row-h text-label text-muted-foreground">
                  {COLUMNS.map((name, i) => (
                    <th key={name} scope="col" className={cn(cell, "border-border bg-card font-medium", i === 0 ? "sticky left-0 z-10 text-left" : "text-right")}>
                      {i === 0 ? (
                        <span className="flex items-center gap-3">
                          <input type="checkbox" aria-label="Select all" checked={all} ref={(el) => void (el && (el.indeterminate = pick.length > 0 && !all))} onChange={() => setSelected(new Set(all ? [] : rows.map((r) => r.product_id)))} className="size-4 accent-brand" />
                          {name}
                        </span>
                      ) : (
                        name
                      )}
                    </th>
                  ))}
                  <th scope="col" className={cn(cell, "border-border bg-card")}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {rows.map((row) => {
                    const p = row.product;
                    const on = selected.has(row.product_id);
                    return (
                      <m.tr key={row.product_id} data-row={row.product_id} exit={{ opacity: 0, transition: { duration: duration.fast } }} className={cn("group row-h hover:bg-(--table-row-hover)", on && PICKED)}>
                        <th scope="row" className={cn(cell, "sticky left-0 z-10 max-w-60 bg-card text-left font-normal group-hover:bg-(--table-row-hover)", on && PICKED)}>
                          <span className="flex items-center gap-3">
                            <input type="checkbox" aria-label={`Select ${p.title}`} checked={on} onChange={() => setSelected((s) => new Set(on ? [...s].filter((id) => id !== row.product_id) : [...s, row.product_id]))} className="size-4 shrink-0 accent-brand" />
                            <Thumb url={p.image_url} className="size-6 shrink-0 rounded-sm" />
                            <Link href={`/products/${p.id}`} title={p.title} className="truncate rounded-sm font-medium text-foreground hover:underline">
                              {p.title}
                            </Link>
                            <Merged row={row} />
                          </span>
                        </th>
                        <td className={cn(cell, "num")}>
                          <Price item={p} now={now} />
                        </td>
                        <td className={cn(cell, "num")}>
                          <Velocity item={p} now={now} />
                        </td>
                        <td className={cn(cell, "num")}>
                          <BestMargin item={p} now={now} />
                        </td>
                        <td className={cn(cell, "num")}>
                          <Metric stat={p.store_count} label="Stores selling it" format={count} now={now} />
                        </td>
                        <td className={cn(cell, "num text-muted-foreground")}>
                          <Added row={row} />
                        </td>
                        <td className={cn(cell, "text-right text-label")}>
                          <Freshness item={p} now={now} paused={NO_PAUSE} />
                        </td>
                        <td className={cn(cell, "w-0 pr-2 text-right")}>
                          <RowMenu row={row} {...actions} />
                        </td>
                      </m.tr>
                    );
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
          <ul aria-label={`${list.name} products`} className="flex flex-col gap-2 md:hidden">
            <AnimatePresence initial={false}>
              {rows.map((row) => {
                const p = row.product;
                return (
                  <m.li key={row.product_id} data-row={row.product_id} layout exit={{ opacity: 0, transition: { duration: duration.fast } }} transition={spring.smooth}>
                    <article className={cn(card, "relative flex items-start gap-3 p-3 zone-data has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-2 has-[a:focus-visible]:outline-ring")}>
                      <Thumb url={p.image_url} className="size-12 shrink-0 rounded-md" />
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <h3 className="line-clamp-2 font-medium text-foreground">
                          <Link href={`/products/${p.id}`} className="outline-none after:absolute after:inset-0">
                            {p.title}
                          </Link>
                        </h3>
                        <Merged row={row} />
                        <dl className="relative z-10 flex flex-wrap gap-x-4 gap-y-1 text-label [&_dt]:text-subtle-foreground">
                          <div className="flex gap-1.5">
                            <dt>Price</dt>
                            <dd>
                              <Price item={p} now={now} />
                            </dd>
                          </div>
                          <div className="flex gap-1.5">
                            <dt>Margin</dt>
                            <dd>
                              <BestMargin item={p} now={now} />
                            </dd>
                          </div>
                        </dl>
                        <p className="text-micro text-subtle-foreground">
                          Added <Added row={row} /> · <Freshness item={p} now={now} paused={NO_PAUSE} />
                        </p>
                      </div>
                      <RowMenu row={row} {...actions} className="relative z-10 -mt-1 -mr-1" />
                    </article>
                  </m.li>
                );
              })}
            </AnimatePresence>
          </ul>
          {items.hasNextPage && (
            <LoadMore
              note={`Showing ${count(rows.length)} of ${count(list.item_count)}`}
              label="Load more"
              more
              pending={items.isFetchingNextPage}
              error={items.isFetchNextPageError ? items.error : null}
              errorTitle="Couldn't load more products"
              onLoad={() => void items.fetchNextPage()}
            />
          )}
        </div>
      )}
      <Toast note={note} />
    </section>
  );
}

function Added({ row }: { row: Row }) {
  return (
    <time dateTime={row.added_at} title={`Added ${formatUtc(row.added_at)}`}>
      {day.format(new Date(row.added_at))}
    </time>
  );
}

/** Merged after it was added: the row reads as the surviving product, once, saying what it was (DEC-314 d). */
function Merged({ row }: { row: Row }) {
  if (!isMerged(row)) return null;
  return (
    <span title={`You added “${row.name}”. It was merged into this product since, so the row shows this one.`} className="relative z-10 w-fit shrink-0">
      <Pill tone="info" icon={GitMerge}>
        Merged
      </Pill>
      <span className="sr-only">: you added {row.name}, since merged into this product</span>
    </span>
  );
}

function MoveMenu({ label, lists, onMove, sub }: { label: string; lists: List[]; onMove: (to: List) => void; sub?: boolean }) {
  const options = lists.length ? (
    lists.map((l) => (
      <DropdownMenu.Item key={l.id} className={menuItem} onSelect={() => onMove(l)}>
        <span className="min-w-0 flex-1 truncate">{l.name}</span>
      </DropdownMenu.Item>
    ))
  ) : (
    <p className="px-2 py-1.5 text-label text-muted-foreground">No other list. Make one with New list.</p>
  );
  if (sub)
    return (
      <DropdownMenu.Sub>
        <DropdownMenu.SubTrigger className={menuItem}>{label}</DropdownMenu.SubTrigger>
        <DropdownMenu.Portal>
          <DropdownMenu.SubContent sideOffset={4} className={menu}>
            {options}
          </DropdownMenu.SubContent>
        </DropdownMenu.Portal>
      </DropdownMenu.Sub>
    );
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button size="sm">{label}</Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className={menu}>
          {options}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function RowMenu({ row, lists, move, remove, className }: { row: Row; lists: List[]; move: (ids: string[], to: List) => void; remove: (ids: string[], title: string) => void; className?: string }) {
  const acted = useRef(false); // a move or remove sends focus to the next row, not back to this gone button
  return (
    <DropdownMenu.Root onOpenChange={(open) => open && (acted.current = false)}>
      <DropdownMenu.Trigger asChild>
        <Button size="icon-sm" variant="ghost" aria-label={`Actions for ${row.product.title}`} className={className}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className={menu} onCloseAutoFocus={(e) => acted.current && e.preventDefault()}>
          <DropdownMenu.Item asChild className={menuItem}>
            <Link href={`/products/${row.product.id}`}>Open product</Link>
          </DropdownMenu.Item>
          <MoveMenu sub label="Move to" lists={lists} onMove={(to) => ((acted.current = true), move([row.product_id], to))} />
          <DropdownMenu.Separator className="my-1 h-px bg-border" />
          <DropdownMenu.Item className={cn(menuItem, "text-negative")} onSelect={() => ((acted.current = true), remove([row.product_id], row.product.title))}>
            Remove
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function NameDialog({ open, list, onClose, onSaved }: { open: boolean; list?: List; onClose: () => void; onSaved: (id: string) => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: async (name: string) => {
      const { data, error } = list
        ? await fetchClient.PATCH("/v1/watchlists/{watchlist_id}", { params: { path: { watchlist_id: list.id } }, body: { name } })
        : await fetchClient.POST("/v1/watchlists", { body: { name } });
      if (!data) throw error;
      return data;
    },
    onSuccess: async (saved) => {
      await refreshWatchlists(client);
      onSaved(saved.id);
      onClose();
    },
  });
  return (
    <Dialog open={open} onOpenChange={(next) => !next && (onClose(), save.reset())}>
      <DialogContent>
        <DialogTitle>{list ? `Rename ${list.name}` : "New list"}</DialogTitle>
        <DialogDescription>{list ? "Its products and alerts stay as they are." : "Move products into it from Main, or tick it in a product's Watch menu."}</DialogDescription>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const name = new FormData(e.currentTarget).get("name")?.toString().trim();
            if (name) save.mutate(name);
          }}
        >
          <input
            name="name"
            aria-label="List name"
            required
            maxLength={80}
            defaultValue={list?.name}
            placeholder="e.g. Q4 gifts"
            aria-invalid={save.isError || undefined}
            aria-describedby={save.isError ? "list-name-error" : undefined}
            className="h-(--button-h-lg) rounded-md border border-border bg-secondary px-3 text-body text-foreground placeholder:text-subtle-foreground aria-invalid:border-negative"
          />
          {save.isError && (
            <p id="list-name-error" role="alert" className="text-label text-negative">
              {reason(save.error)}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button type="submit" variant="primary" aria-disabled={save.isPending}>
              {list ? "Rename" : "Create list"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({ list, onClose }: { list?: List; onClose: () => void }) {
  const client = useQueryClient();
  const remove = useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await fetchClient.DELETE("/v1/watchlists/{watchlist_id}", { params: { path: { watchlist_id: id } } });
      if (!data) throw error;
    },
    onSuccess: async () => {
      window.history.replaceState(null, "", window.location.pathname);
      await refreshWatchlists(client, true);
      onClose();
    },
  });
  const n = list?.item_count ?? 0;
  return (
    <Dialog open={list !== undefined} onOpenChange={(next) => !next && (onClose(), remove.reset())}>
      <DialogContent>
        <DialogTitle>Delete {list?.name}?</DialogTitle>
        <DialogDescription>
          {n === 0 ? "It's empty." : `Its ${count(n)} ${n === 1 ? "product leaves" : "products leave"} with it; they stay on any other list.`}
          {list?.name === "Main" && " The next ★ makes a new Main."} This can&apos;t be undone.
        </DialogDescription>
        {remove.isError && (
          <p role="alert" className="text-label text-negative">
            {reason(remove.error)}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button variant="destructive" aria-disabled={remove.isPending} onClick={() => list && !remove.isPending && remove.mutate(list.id)}>
            Delete list
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** A result, with Undo while it can; polite, so it never takes focus (vault Design/UI States, Success / undo). */
function Toast({ note }: { note: Note | null }) {
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-20 z-40 flex justify-center lg:bottom-6">
      <AnimatePresence>
        {note && (
          <m.div
            key={note.text}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: duration.fast } }}
            transition={{ duration: duration.base, ease: ease.out }}
            className="pointer-events-auto flex max-w-xl items-center gap-3 rounded-lg border border-border bg-popover px-4 py-2.5 text-data text-popover-foreground shadow-dialog"
          >
            <span>{note.text}</span>
            {note.undo && (
              <Button size="sm" variant="ghost" aria-keyshortcuts="Control+Z" onClick={note.undo}>
                Undo
              </Button>
            )}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div role="status" aria-label="Loading products" className={cn(card, "overflow-hidden")}>
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} className="row-h flex items-center gap-3 border-b border-border-subtle px-3 last:border-0">
          <Skeleton className="size-6 shrink-0 rounded-sm" />
          <Skeleton className="h-3.5 w-56 max-w-1/2" />
          <Skeleton className="ml-auto h-3.5 w-14 max-md:hidden" />
          <Skeleton className="h-3.5 w-14 max-md:hidden" />
          <Skeleton className="h-3.5 w-14" />
        </div>
      ))}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="grid items-start gap-4 md:grid-cols-[12rem_minmax(0,1fr)]">
      <div className="flex flex-col gap-1.5 max-md:hidden" aria-hidden>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-8 rounded-md" />
        ))}
      </div>
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-40" />
        <TableSkeleton />
      </div>
    </div>
  );
}
