"use client";

import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, DatabaseZap, Filter, TriangleAlert } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, fetchClient, isProblem } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { duration, ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { Compare, CompareSkeleton, Thumb } from "./compare";
import { MergeDialog, SplitDialog } from "./dialogs";
import { bands, keyAction, LEGEND, nextAfter, pairLabel, sourceLabel, step, type Cluster, type QueueItem } from "./model";

const LIST = "/v1/admin/matching/candidates";
const DETAIL = "/v1/admin/matching/candidates/{candidate_id}";
type Sort = "impact" | "score" | "age";
interface Filters {
  sort: Sort;
  pair: string;
  band: string;
  version: string;
  min?: number; // the band's bounds, read from the scorer's thresholds when it was picked
  max?: number;
}
const NO_FILTERS: Filters = { sort: "impact", pair: "", band: "", version: "" };
interface Undoable {
  id: number;
  label: string;
  item?: QueueItem; // put back in the queue on undo
}
interface Note {
  text: string;
  tone: "done" | "error";
  undo?: boolean;
}

const detailOptions = (id: number) => $api.queryOptions("get", DETAIL, { params: { path: { candidate_id: id } } });
const reasonOf = (error: unknown) => (isProblem(error) ? error.detail : "The API didn't answer. Check that it is running, then try again.");

// UX-1 (DEC-263): one key per decision. A decision hides its pair and selects the next one before the request
// returns, so the owner never waits on the network or an animation; a failed request puts the pair back.
export function MatchingQueue() {
  const ready = useApiReady();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const list = $api.useInfiniteQuery(
    "get",
    LIST,
    {
      params: {
        query: {
          sort: filters.sort,
          source_pair: filters.pair || undefined,
          version: filters.version || undefined,
          min_score: filters.min,
          max_score: filters.max,
          limit: 50,
        },
      },
    },
    // null, not undefined: openapi-react-query sends an undefined page param as a cursor.
    { enabled: ready, pageParamName: "cursor", initialPageParam: null, getNextPageParam: (page) => page.next_cursor, staleTime: 30_000 },
  );
  const first = list.data?.pages[0];
  const [hidden, setHidden] = useState<ReadonlySet<number>>(new Set());
  const items = useMemo(() => {
    const seen = new Set<number>();
    return (list.data?.pages ?? []).flatMap((page) => page.items).filter((item) => !hidden.has(item.id) && !seen.has(item.id) && seen.add(item.id));
  }, [list.data, hidden]);
  const ids = useMemo(() => items.map((item) => item.id), [items]);
  const [selected, setSelected] = useState<number | null>(null);
  const current = selected != null && ids.includes(selected) ? selected : (ids[0] ?? null);
  const at = current == null ? -1 : ids.indexOf(current);
  const detail = $api.useQuery("get", DETAIL, { params: { path: { candidate_id: current ?? 0 } } }, { enabled: ready && current != null });
  const shown = detail.data?.id === current ? detail.data : undefined;
  const [image, setImage] = useState(0);
  const [imageFor, setImageFor] = useState(current);
  if (imageFor !== current) {
    setImageFor(current);
    setImage(0);
  }
  const [history, setHistory] = useState<Undoable[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [dialog, setDialog] = useState<"merge" | "split" | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  // The next two pairs load in the background, and the next page well before the end.
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list;
  useEffect(() => {
    for (const id of ids.slice(at + 1, at + 3)) void queryClient.prefetchQuery(detailOptions(id));
    if (hasNextPage && !isFetchingNextPage && ids.length - at < 10) void fetchNextPage();
  }, [ids, at, hasNextPage, isFetchingNextPage, fetchNextPage, queryClient]);

  useEffect(() => {
    if (!note) return;
    const timer = setTimeout(() => setNote(null), note.tone === "error" ? 10_000 : 6_000);
    return () => clearTimeout(timer);
  }, [note]);

  const hide = (id: number, show: boolean) =>
    setHidden((s) => {
      const next = new Set(s);
      if (show) next.delete(id);
      else next.add(id);
      return next;
    });
  const move = (id: number) => (setSelected(nextAfter(ids, id)), hide(id, false));

  // A pair decided elsewhere, or whose sides already share a product, is skipped without a key.
  const [skipped, setSkipped] = useState<number | null>(null);
  if (shown?.superseded && skipped !== shown.id) {
    setSkipped(shown.id);
    move(shown.id);
    setNote({ tone: "done", text: `Pair #${shown.id} was superseded by another decision, so it was skipped.` });
  }

  const refresh = () => queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[1]).startsWith("/v1/admin/matching/") });

  const decide = async (action: "accept" | "reject") => {
    const item = items.find((i) => i.id === current);
    if (!item) return;
    move(item.id);
    const label = action === "accept" ? "Accepted" : "Rejected";
    const { data, error, response } = await fetchClient.POST("/v1/admin/matching/decisions", { body: { action, candidate_id: item.id } });
    if (data) {
      if (data.id != null) setHistory((h) => [...h, { id: data.id!, label: `${label} pair #${item.id}`, item }]);
      setNote({ tone: "done", text: `${label} pair #${item.id}.`, undo: data.id != null });
      void queryClient.invalidateQueries({ queryKey: detailOptions(item.id).queryKey });
    } else if (response?.status === 409) {
      setNote({ tone: "done", text: `Pair #${item.id} was already decided, so it was skipped.` });
    } else {
      hide(item.id, true);
      setNote({ tone: "error", text: `Couldn't save "${action}" for pair #${item.id}: ${reasonOf(error)} It's back in the queue.` });
    }
  };

  const undo = async () => {
    const last = history.at(-1);
    if (!last) return setNote({ tone: "done", text: "Nothing to undo yet." });
    setHistory((h) => h.slice(0, -1));
    const { error } = await fetchClient.POST("/v1/admin/matching/decisions/{decision_id}/undo", { params: { path: { decision_id: last.id } } });
    if (error) return setNote({ tone: "error", text: `Couldn't undo: ${reasonOf(error)}` });
    if (last.item) {
      hide(last.item.id, true);
      setSelected(last.item.id);
    }
    await refresh();
    setNote({ tone: "done", text: `Undone: ${last.label}. The log keeps both decisions.` });
  };

  const product = async (body: { action: "merge"; product_id: string; into: string } | { action: "split" | "unlink"; listing_ids: number[] }, label: string) => {
    const { data, error } = await fetchClient.POST("/v1/admin/matching/decisions", { body });
    if (!data) return reasonOf(error);
    if (data.id != null) setHistory((h) => [...h, { id: data.id!, label }]);
    setDialog(null);
    await refresh();
    setNote({ tone: "done", text: `${label}.`, undo: data.id != null });
    return null;
  };
  const merge = (from: Cluster, into: Cluster) => product({ action: "merge", product_id: from.product_id, into: into.product_id }, `Merged ${from.name} into ${into.name}`);
  const split = (action: "split" | "unlink", cluster: Cluster, listingIds: number[]) =>
    product({ action, listing_ids: listingIds }, `${action === "split" ? "Split" : "Unlinked"} ${listingIds.length} from ${cluster.name}`);

  const canMerge = shown?.clusters.length === 2;
  const canSplit = !!shown?.clusters.some((c) => c.listings > 1);
  const act = (type: ReturnType<typeof keyAction>) => {
    if (!type) return;
    if (type.type === "next" || type.type === "prev") return setSelected(step(ids, current, type.type === "next" ? 1 : -1));
    if (type.type === "undo") return void undo();
    if (type.type === "image") return setImage(type.index);
    if (type.type === "skip") {
      const next = step(ids, current, 1);
      return setSelected(next === current ? (ids[0] ?? null) : next); // the last pair wraps to the first
    }
    // Decide on what is on screen, never on a pair still loading.
    if (!shown) return current != null && setNote({ tone: "done", text: `Pair #${current} is still loading.` });
    if (type.type === "accept" || type.type === "reject") return void decide(type.type);
    if (type.type === "merge") return canMerge ? setDialog("merge") : setNote({ tone: "done", text: "Merge needs both listings on products. Accept links them instead." });
    if (type.type === "split") return canSplit ? setDialog("split") : setNote({ tone: "done", text: "Split needs a product with two listings or more." });
  };
  const onKeyDown = useEffectEvent((e: KeyboardEvent) => {
    if (dialog || e.defaultPrevented) return;
    const action = keyAction(e);
    if (!action) return;
    e.preventDefault();
    act(action);
  });
  useEffect(() => {
    const listener = (e: KeyboardEvent) => onKeyDown(e);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  if (!first) {
    return list.isError ? (
      <section aria-label="Matching queue" className="rounded-xl border border-border bg-card shadow-card">
        <PanelError title="Couldn't load the queue" headingLevel="h2" size="md" error={list.error} retry={() => void list.refetch()} />
      </section>
    ) : (
      <Layout list={<ListSkeleton />} compare={<CompareSkeleton />} />
    );
  }

  const { summary, facets, thresholds } = first;
  const filtered = filters.pair !== "" || filters.band !== "" || filters.version !== "";
  const stale = list.isRefetchError && <StaleLine what="queue" error={list.error} asOf={list.dataUpdatedAt} retry={() => void list.refetch()} boxed />;
  let body: React.ReactNode;
  if (items.length === 0 && list.isFetchingNextPage) body = <Layout list={<ListSkeleton />} compare={<CompareSkeleton />} />;
  else if (items.length === 0)
    body = (
      <section aria-label="Matching queue" className="rounded-xl border border-border bg-card shadow-card">
        {filtered && summary.pending > 0 ? (
          <EmptyState icon={Filter} title="No pairs match these filters" headingLevel="h2" action={<Button onClick={() => setFilters({ ...NO_FILTERS, sort: filters.sort })}>Clear filters</Button>}>
            {summary.pending} {summary.pending === 1 ? "pair is" : "pairs are"} queued in all.
          </EmptyState>
        ) : summary.stored_sources.length < 2 && hidden.size === 0 ? (
          <EmptyState
            icon={DatabaseZap}
            title="Matching needs at least two stored sources"
            headingLevel="h2"
            action={
              <Button asChild>
                <Link href="/admin/data-health">Open Data Health</Link>
              </Button>
            }
          >
            <p>
              {summary.stored_sources.length === 0
                ? "No source has stored a listing yet."
                : `Only ${summary.stored_sources.map(sourceLabel).join(", ")} listings are stored today.`}{" "}
              The matcher pairs listings across stored sources, so a second one, such as a CSV import, gives it pairs to compare. AliExpress is a live lookup only and is never
              matched.
            </p>
          </EmptyState>
        ) : (
          <EmptyState icon={CircleCheck} title="Queue clear" headingLevel="h2">
            <p>
              {hidden.size > 0 ? `You decided ${hidden.size} ${hidden.size === 1 ? "pair" : "pairs"} this session. ` : ""}
              {summary.last_auto_link_at
                ? `The matcher has auto-linked ${summary.auto_linked.toLocaleString("en-US")} listings; the last on ${formatUtc(summary.last_auto_link_at)}.`
                : "The matcher hasn't auto-linked a listing yet."}
              {!summary.matcher_enabled && " It is off (MATCHER_ENABLED), so nothing new queues until it runs."}
            </p>
          </EmptyState>
        )}
      </section>
    );
  else
    body = (
      <Layout
        list={
          <QueueList
            items={items}
            current={current}
            onSelect={setSelected}
            loadingMore={list.isFetchingNextPage}
            more={list.hasNextPage}
            total={summary.pending - hidden.size}
          />
        }
        compare={
          <section aria-label="Compare" className="flex min-w-0 flex-col gap-4">
            <DecisionBar shown={!!shown} canMerge={canMerge} canSplit={canSplit} canUndo={history.length > 0} act={act} />
            {shown ? (
              <Compare detail={shown} image={image} now={now} />
            ) : detail.isError ? (
              <div className="rounded-xl border border-border bg-card">
                <EmptyState
                  icon={TriangleAlert}
                  tone="error"
                  title={`Couldn't load pair #${current}`}
                  headingLevel="h2"
                  action={
                    <Button variant="primary" onClick={() => void detail.refetch()}>
                      Retry
                    </Button>
                  }
                >
                  <p>{reasonOf(detail.error)} Skip to the next one with J.</p>
                </EmptyState>
              </div>
            ) : (
              <CompareSkeleton />
            )}
          </section>
        }
      />
    );

  return (
    <div className="flex flex-col gap-4">
      <Toolbar filters={filters} setFilters={setFilters} facets={facets} thresholds={thresholds} />
      {stale}
      {body}
      <Toast note={note} onUndo={() => void undo()} />
      {shown && (
        <>
          <MergeDialog clusters={shown.clusters} open={dialog === "merge"} onOpenChange={(open) => setDialog(open ? "merge" : null)} onConfirm={merge} />
          <SplitDialog clusters={shown.clusters} open={dialog === "split"} onOpenChange={(open) => setDialog(open ? "split" : null)} onConfirm={split} />
        </>
      )}
    </div>
  );
}

function Layout({ list, compare }: { list: React.ReactNode; compare: React.ReactNode }) {
  // Desktop: the 360 px queue left of the pair. Phone: the pair first, the queue under it.
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <div className="order-2 min-w-0 lg:order-none">{list}</div>
      <div className="order-1 min-w-0 lg:order-none">{compare}</div>
    </div>
  );
}

const selectClass =
  "h-(--button-h-sm) min-w-0 rounded-md border border-border bg-secondary px-2 text-label text-foreground hover:border-border-strong";

function Toolbar({
  filters,
  setFilters,
  facets,
  thresholds,
}: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  facets: { source_pairs: string[]; versions: string[] };
  thresholds: { auto_link: number; queue: number };
}) {
  const field = (key: keyof Filters, label: string, options: { value: string; label: string }[]) => (
    <label className="flex min-w-0 flex-col gap-1 text-micro font-medium text-muted-foreground uppercase">
      {label}
      <select
        className={selectClass}
        value={filters[key]}
        onChange={(e) => {
          const band = key === "band" ? bands(thresholds).find((b) => b.value === e.target.value) : undefined;
          setFilters({ ...filters, [key]: e.target.value, ...(key === "band" && { min: band?.min, max: band?.max }) });
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <div role="group" aria-label="Sort and filter" className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-end">
      {field("sort", "Sort", [
        { value: "impact", label: "Impact first" },
        { value: "score", label: "Highest score" },
        { value: "age", label: "Oldest first" },
      ])}
      {field("pair", "Sources", [{ value: "", label: "All pairs" }, ...facets.source_pairs.map((p) => ({ value: p, label: pairLabel(p) }))])}
      {field("band", "Score", [{ value: "", label: "Any score" }, ...bands(thresholds).map((b) => ({ value: b.value, label: b.label }))])}
      {field("version", "Matcher", [{ value: "", label: "Any version" }, ...facets.versions.map((v) => ({ value: v, label: v }))])}
    </div>
  );
}

function QueueList({
  items,
  current,
  onSelect,
  loadingMore,
  more,
  total,
}: {
  items: QueueItem[];
  current: number | null;
  onSelect: (id: number) => void;
  loadingMore: boolean;
  more: boolean;
  total: number;
}) {
  const active = useRef<HTMLButtonElement>(null);
  useEffect(() => active.current?.scrollIntoView({ block: "nearest" }), [current]);
  // Rows never animate: a decided row leaves at once (vault Design/Motion System).
  return (
    <section aria-labelledby="queue-title" className="flex flex-col rounded-xl border border-border bg-card shadow-card">
      <h2 id="queue-title" className="flex items-baseline justify-between border-b border-border px-4 py-3 text-title-3 font-semibold">
        Queue
        <span className="font-mono text-label font-normal tabular-nums text-muted-foreground">{Math.max(total, items.length)} pending</span>
      </h2>
      <ol className="flex max-h-[min(70vh,44rem)] flex-col overflow-y-auto p-1">
        {items.map((item) => {
          const selected = item.id === current;
          return (
            <li key={item.id}>
              <button
                ref={selected ? active : undefined}
                onClick={() => onSelect(item.id)}
                aria-current={selected ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-left hover:bg-accent",
                  selected && "bg-selected shadow-[inset_2px_0_0_var(--brand)] hover:bg-selected",
                )}
              >
                <span className="flex shrink-0 -space-x-2">
                  <Thumb url={item.a.image_url} className="size-9 rounded-md border-2 border-card" />
                  <Thumb url={item.b.image_url} className="size-9 rounded-md border-2 border-card" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-data text-foreground">{item.a.title}</span>
                  <span className="flex items-center gap-1.5 truncate text-label text-subtle-foreground">
                    {sourceLabel(item.a.source)} ↔ {sourceLabel(item.b.source)}
                    {item.impact && (
                      <span className="rounded-sm bg-info/12 px-1 text-micro font-medium text-info" title="You have notes or tags on one side's product">
                        Noted
                      </span>
                    )}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-data tabular-nums text-foreground">{item.score.toFixed(2)}</span>
              </button>
            </li>
          );
        })}
        {(loadingMore || more) && (
          <li className="px-2.5 py-2 text-label text-subtle-foreground" aria-live="polite">
            {loadingMore ? "Loading more…" : "More load as you go."}
          </li>
        )}
      </ol>
    </section>
  );
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border bg-card p-2 shadow-card" aria-hidden>
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2">
          <Skeleton className="size-9 rounded-md" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-2.5 w-2/5" />
          </div>
          <Skeleton className="h-3 w-8" />
        </div>
      ))}
    </div>
  );
}

function DecisionBar({
  shown,
  canMerge,
  canSplit,
  canUndo,
  act,
}: {
  shown: boolean;
  canMerge: boolean;
  canSplit: boolean;
  canUndo: boolean;
  act: (a: ReturnType<typeof keyAction>) => void;
}) {
  const button = (type: "accept" | "reject" | "skip" | "merge" | "split" | "undo", label: string, key: string, variant: "primary" | "secondary" | "ghost", enabled: boolean, desktop = false) => (
    <Button variant={variant} size="sm" aria-disabled={!enabled} onClick={() => enabled && act({ type })} aria-keyshortcuts={key} className={cn(desktop && "hidden lg:inline-flex")}>
      {label}
      <Kbd className="hidden lg:inline-flex">{key}</Kbd>
    </Button>
  );
  return (
    <div role="toolbar" aria-label="Decision" className="sticky top-2 z-10 flex flex-wrap items-center gap-1.5 rounded-xl border border-border bg-card/95 p-2 shadow-card backdrop-blur">
      {button("accept", "Accept", "A", "primary", shown)}
      {button("reject", "Reject", "R", "secondary", shown)}
      {button("skip", "Skip", "S", "ghost", true)}
      <span className="mx-1 hidden h-5 w-px bg-border lg:block" aria-hidden />
      {button("merge", "Merge", "M", "ghost", shown && canMerge, true)}
      {button("split", "Split", "X", "ghost", shown && canSplit, true)}
      {button("undo", "Undo", "U", "ghost", canUndo, true)}
      <p className="ml-auto hidden items-center gap-1 text-micro text-subtle-foreground xl:flex">
        {LEGEND.slice(6).map((entry) => (
          <span key={entry.label} className="flex items-center gap-1">
            {entry.keys.map((k) => (
              <Kbd key={k}>{k}</Kbd>
            ))}
            {entry.label}
          </span>
        ))}
      </p>
      <span className="sr-only">Keys: {LEGEND.map((l) => `${l.keys.join(" or ")} ${l.label}`).join(", ")}.</span>
    </div>
  );
}

/** The undo toast slides up (transform), honours reduced motion, and never blocks a key. */
function Toast({ note, onUndo }: { note: Note | null; onUndo: () => void }) {
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-20 z-40 flex justify-center lg:bottom-6">
      <AnimatePresence>
        {note && (
          <m.div
            key={note.text}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: duration.fast } }}
            transition={{ duration: duration.slow, ease: ease.out }}
            className={cn(
              "pointer-events-auto flex max-w-xl items-center gap-3 rounded-lg border bg-popover px-4 py-2.5 text-data text-popover-foreground shadow-dialog",
              note.tone === "error" ? "border-negative/40" : "border-border",
            )}
          >
            <span>{note.text}</span>
            {note.undo && (
              <Button size="sm" variant="ghost" onClick={onUndo}>
                Undo <Kbd>U</Kbd>
              </Button>
            )}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}
