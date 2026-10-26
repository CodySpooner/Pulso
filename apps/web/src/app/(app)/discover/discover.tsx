"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, useReducedMotion } from "motion/react";
import * as m from "motion/react-m";
import { Compass, Factory, LayoutGrid, Rows3, SearchX, SlidersHorizontal, Store, TriangleAlert, X } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUtc } from "@/lib/format";
import { duration, spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { ExportCsv, useCsvExport } from "./export-csv";
import { StarButton } from "../watchlists/star";
import { CardSkeletons, feedColumns, GRID, ProductCard, ProductTable, TableSkeleton, type Item, type Paused } from "./feed-views";
import {
  activeFilters,
  apiQuery,
  feedSearch,
  FIRST_SEEN,
  joinPages,
  NO_FILTERS,
  parseFeed,
  readView,
  saveView,
  SORTS,
  SOURCES,
  type FeedState,
  type Filters,
  type View,
} from "./url-state";

const noSubscribe = () => () => {};
const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
const control =
  "h-(--button-h-md) min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) hover:border-border-strong";

// UX-2 (vault Features/Discover): the feed, its filters, sort and two views. The URL holds the state; replacing it
// keeps Back for the previous page and skips a server round trip (DEC-238 e). States per vault Design/UI States.
export function Discover() {
  const params = useSearchParams();
  const state = parseFeed(params);
  const remembered = useSyncExternalStore(noSubscribe, readView, () => null);
  const view: View = state.view ?? remembered ?? "grid";
  const set = useCallback((next: Partial<FeedState>) => {
    const search = feedSearch({ ...parseFeed(new URLSearchParams(window.location.search)), ...next });
    window.history.replaceState(null, "", search ? `?${search}` : window.location.pathname);
  }, []);
  const setView = useCallback(
    (next: View) => {
      saveView(next);
      set({ view: next });
    },
    [set],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "v" || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      e.preventDefault();
      setView(view === "grid" ? "table" : "grid");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, setView]);

  const feed = $api.useInfiniteQuery(
    "get",
    "/v1/products",
    { params: { query: apiQuery(state) } },
    {
      enabled: useApiReady(),
      pageParamName: "cursor",
      // null, not undefined: openapi-react-query sends an undefined page param as cursor=0 (DEC-166).
      initialPageParam: null,
      getNextPageParam: (page) => page.next_cursor,
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  const { data, error, hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = feed;
  const items: Item[] = joinPages(data?.pages);
  const first = data?.pages[0];
  const now = feed.dataUpdatedAt;
  const paused = new Map(first?.degraded.filter((d) => d.state !== "stale").map((d) => [d.source, SAID[d.state]]));
  const more = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage && !isFetchNextPageError) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage]);
  const filters = activeFilters(state);
  // The page names the filter's store or supplier; an id it doesn't know reads as such once it has answered.
  const named: Named = (key) => first?.[key]?.name ?? `#${state[key]}${first ? ", not found" : ""}`;
  const csv = useCsvExport(apiQuery(state));
  const empty = !!first && items.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <Toolbar state={state} set={set} view={view} setView={setView}>
        <VendorChips state={state} set={set} named={named} loading={!first && !feed.isError} />
      </Toolbar>
      {/* The count, and what Export CSV takes: every matching row, not the loaded pages (DEC-316). */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="min-w-0 flex-1 text-label text-subtle-foreground" aria-live="polite">
          {first ? (
            <>
              {items.length.toLocaleString("en-US")} {items.length === 1 ? "product" : "products"}
              {hasNextPage && " loaded, more as you scroll"} ·{" "}
              {first.as_of ? (
                <>
                  as of <time dateTime={first.as_of}>{formatUtc(first.as_of)}</time>
                </>
              ) : (
                "nothing collected yet"
              )}
            </>
          ) : (
            " "
          )}
        </p>
        <ExportCsv csv={csv} empty={empty} />
      </div>
      {first && first.degraded.length > 0 && <DegradedBanner degraded={first.degraded} />}
      {data && feed.isRefetchError && <StaleLine boxed what="Couldn't refresh the feed" error={error} asOf={now} retry={() => void feed.refetch()} />}
      <m.div
        key={view}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: duration.fast }}
        // E exports while focus is in the results, grid or table (vault Features/CSV Export & Import).
        onKeyDown={(e) => {
          if (e.key.toLowerCase() !== "e" || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target) || empty) return;
          e.preventDefault();
          void csv.run();
        }}
      >
        {!data ? (
          feed.isError ? (
            <section className="rounded-xl border border-border bg-card shadow-card">
              <PanelError headingLevel="h2" size="md" title="Couldn't load products" error={error} retry={() => void feed.refetch()} />
            </section>
          ) : (
            <>
              <span className="sr-only" role="status">
                Loading products…
              </span>
              {view === "grid" ? (
                <div className={GRID}>
                  <CardSkeletons n={12} />
                </div>
              ) : (
                <TableSkeleton />
              )}
            </>
          )
        ) : items.length === 0 ? (
          <Empty state={state} set={set} filters={filters} named={named} />
        ) : view === "grid" ? (
          <Grid items={items} now={now} paused={paused} loadingMore={isFetchingNextPage} onNearEnd={more} />
        ) : (
          <ProductTable items={items} columns={feedColumns(now, paused)} lead={(item) => <StarButton product={item} className="-ml-1.5" />} loadingMore={isFetchingNextPage} onNearEnd={more} />
        )}
      </m.div>
      {isFetchNextPageError && (
        <section className="rounded-xl border border-border bg-card shadow-card">
          <PanelError headingLevel="h2" title="Couldn't load more products" error={error} retry={() => void fetchNextPage()} />
        </section>
      )}
    </div>
  );
}

function Grid({ items, now, paused, loadingMore, onNearEnd }: { items: Item[]; now: number; paused: Paused; loadingMore: boolean; onNearEnd: () => void }) {
  const sentinel = useRef<HTMLDivElement>(null);
  // Re-observed after each page, so a sentinel still in view after a short page asks for the next one.
  useEffect(() => {
    const io = new IntersectionObserver(([entry]) => entry.isIntersecting && onNearEnd(), { rootMargin: "800px 0px" });
    io.observe(sentinel.current!);
    return () => io.disconnect();
  }, [items.length, onNearEnd]);
  return (
    <>
      <ul className={GRID} aria-label="Products">
        {items.map((item) => (
          <li key={item.id} className="flex">
            <ProductCard item={item} now={now} paused={paused} />
          </li>
        ))}
        {loadingMore && <CardSkeletons n={6} />}
      </ul>
      <div ref={sentinel} aria-hidden />
    </>
  );
}

function ViewToggle({ view, setView }: { view: View; setView: (v: View) => void }) {
  const options = [
    { value: "grid", label: "Grid", icon: LayoutGrid },
    { value: "table", label: "Table", icon: Rows3 },
  ] as const;
  return (
    <div role="group" aria-label="View, V switches" className="relative flex h-(--button-h-md) shrink-0 rounded-md border border-border bg-secondary p-0.5">
      {options.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          aria-pressed={view === value}
          onClick={() => setView(value)}
          className={cn(
            "relative hit-area flex items-center gap-1.5 rounded-sm px-2.5 text-label font-medium transition-colors duration-(--duration-fast)",
            view === value ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {view === value && <m.span layoutId="discover-view" transition={spring.snappy} className="absolute inset-0 rounded-sm segment-thumb" />}
          <Icon className="relative size-3.5" aria-hidden />
          <span className="relative">{label}</span>
        </button>
      ))}
    </div>
  );
}

function Toolbar({
  state,
  set,
  view,
  setView,
  children,
}: {
  state: FeedState;
  set: (next: Partial<FeedState>) => void;
  view: View;
  setView: (v: View) => void;
  /** The store and supplier chips, a row of their own under the filters at every width. */
  children: React.ReactNode;
}) {
  const [sheet, setSheet] = useState(false);
  const n = activeFilters(state).length;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Field label="Sort">
        <select aria-label="Sort" className={control} value={state.sort} onChange={(e) => set({ sort: e.target.value as FeedState["sort"] })}>
          {Object.entries(SORTS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Button className="md:hidden" onClick={() => setSheet(true)}>
        <SlidersHorizontal aria-hidden />
        Filters{n > 0 && ` (${n})`}
      </Button>
      <div className="ml-auto">
        <ViewToggle view={view} setView={setView} />
      </div>
      {/* Sort and view on the first row, the filters on their own row below. */}
      <div className="flex basis-full flex-wrap items-center gap-2 max-md:hidden">
        <FilterFields state={state} set={set} />
      </div>
      {children}
      <Sheet open={sheet} onOpenChange={setSheet}>
        <SheetContent side="bottom" closeLabel="Close filters" className="gap-4 px-4 pt-4 pb-4 md:hidden">
          <SheetTitle className="text-title-3 font-semibold">Filters</SheetTitle>
          <SheetDescription className="sr-only">Results update as you change a filter.</SheetDescription>
          <div className="flex flex-col gap-3 overflow-y-auto [&_label]:justify-between [&_select]:w-48">
            <FilterFields state={state} set={set} />
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" className="flex-1" disabled={n === 0} onClick={() => set(NO_FILTERS)}>
              Clear filters
            </Button>
            <Button variant="primary" className="flex-1" onClick={() => setSheet(false)}>
              Show results
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

/** A visible label beside its control; each control names itself with aria-label, since a label wrapping a select
 *  would add the selected option to its name. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex items-center gap-2">
      <span aria-hidden className="text-label text-muted-foreground">
        {label}
      </span>
      {children}
    </label>
  );
}

const dollars = (raw: string) => (/^\d{1,7}$/.test(raw.trim()) ? Number(raw.trim()) : null);

function FilterFields({ state, set }: { state: FeedState; set: (next: Partial<FeedState>) => void }) {
  const categories = $api.useQuery("get", "/v1/categories", {}, { enabled: useApiReady(), staleTime: 5 * 60_000 });
  // Typed prices apply on Enter or leaving the box, not on each keystroke.
  const price = (key: "price_min" | "price_max", label: string) => (
    <input
      key={`${key}-${state[key]}`}
      type="number"
      inputMode="numeric"
      min={0}
      step={1}
      placeholder={label}
      aria-label={`${label} price, USD`}
      defaultValue={state[key] ?? ""}
      onBlur={(e) => dollars(e.currentTarget.value) !== state[key] && set({ [key]: dollars(e.currentTarget.value) })}
      onKeyDown={(e) => e.key === "Enter" && set({ [key]: dollars(e.currentTarget.value) })}
      className={cn(control, "w-20 tabular-nums placeholder:text-subtle-foreground")}
    />
  );
  const choose = <K extends keyof Filters>(key: K, label: string, parse: (raw: string) => Filters[K]) => ({
    "aria-label": label,
    className: control,
    value: String(state[key] ?? ""),
    onChange: (e: React.ChangeEvent<HTMLSelectElement>) => set({ [key]: e.target.value === "" ? null : parse(e.target.value) }),
  });
  return (
    <>
      <Field label="Category">
        <select {...choose("category", "Category", Number)} className={cn(control, "max-w-56")}>
          <option value="">All</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.path.replaceAll(" > ", " › ")}
            </option>
          ))}
          {state.category !== null && !categories.data?.some((c) => c.id === state.category) && <option value={state.category}>Category #{state.category}</option>}
        </select>
      </Field>
      <Field label="Price">
        <span className="flex items-center gap-1">
          {price("price_min", "Min")}
          <span aria-hidden className="text-subtle-foreground">–</span>
          {price("price_max", "Max")}
        </span>
      </Field>
      <Field label="Source">
        <select {...choose("source", "Source", (v) => v as Filters["source"])}>
          <option value="">All</option>
          {Object.entries(SOURCES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="First seen">
        <select {...choose("first_seen_days", "First seen", (v) => Number(v) as Filters["first_seen_days"])}>
          <option value="">Any time</option>
          {FIRST_SEEN.map((d) => (
            <option key={d} value={d}>
              Last {d} days
            </option>
          ))}
        </select>
      </Field>
      <Field label="Stores">
        <select {...choose("has_sellers", "Stores", (v) => v === "true")}>
          <option value="">Any</option>
          <option value="true">Sold by stores</option>
          <option value="false">No stores yet</option>
        </select>
      </Field>
    </>
  );
}

type Vendor = "store" | "supplier";
type Named = (key: Vendor) => string;

const FILTER_LABELS: Record<keyof Filters, (s: Filters, named: Named) => string> = {
  category: () => "Category",
  price_min: (s) => `Price ≥ $${s.price_min}`,
  price_max: (s) => `Price ≤ $${s.price_max}`,
  source: (s) => `Source: ${s.source ? SOURCES[s.source] : ""}`,
  first_seen_days: (s) => `First seen in the last ${s.first_seen_days} days`,
  has_sellers: (s) => (s.has_sellers ? "Sold by stores" : "No stores yet"),
  store: (_, named) => `Store: ${named("store")}`,
  supplier: (_, named) => `Supplier: ${named("supplier")}`,
};

const VENDORS = { store: { label: "Store", icon: Store }, supplier: { label: "Supplier", icon: Factory } } as const;

/** The store and supplier filters have no control (a palette row sets them, imp-242), so each shows as a removable chip
 *  with its name; chips leave with the layout-reflow pattern (Motion System pattern 5). */
function VendorChips({ state, set, named, loading }: { state: FeedState; set: (next: Partial<FeedState>) => void; named: Named; loading: boolean }) {
  const list = useRef<HTMLUListElement>(null);
  // Reduced motion keeps the fade only: MotionConfig would snap the scale, a one-frame jump in size.
  const gone = useReducedMotion() ? { opacity: 0 } : { opacity: 0, scale: 0.9 };
  const shown = (Object.keys(VENDORS) as Vendor[]).filter((key) => state[key] !== null);
  const remove = (key: Vendor, button: HTMLButtonElement) => {
    // Focus stays with the filters: the other chip's remove button, else the page heading, as after a navigation. The
    // removed chip is still in the list while it exits, so it's skipped by reference.
    const other = [...(list.current?.querySelectorAll("button") ?? [])].find((b) => b !== button);
    (other ?? list.current?.closest("main")?.querySelector<HTMLElement>("h1"))?.focus({ preventScroll: true });
    set({ [key]: null });
  };
  return (
    <ul ref={list} aria-label="Store and supplier filters" className="flex basis-full flex-wrap gap-2 empty:hidden">
      <AnimatePresence initial={false}>
        {shown.map((key) => {
          const { label, icon: Icon } = VENDORS[key];
          return (
            <m.li
              key={key}
              layout
              layoutDependency={shown.join()} // reflow when a chip leaves, never when a name loads
              initial={gone}
              animate={{ opacity: 1, scale: 1 }}
              exit={gone}
              transition={spring.smooth}
              className="flex h-(--button-h-sm) max-w-full min-w-0 items-center gap-1.5 rounded-md border border-border bg-secondary pl-2.5 text-label"
            >
              <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              <span className="text-muted-foreground">{label}</span>
              {loading ? (
                <>
                  {/* --skeleton is the chip's own --secondary in dark, so the bar takes a foreground tint. */}
                  <Skeleton className="h-3 w-28 bg-foreground/10" />
                  <span className="sr-only">loading</span>
                </>
              ) : (
                <span className="min-w-0 truncate font-medium text-foreground" title={named(key)}>
                  {named(key)}
                </span>
              )}
              <button
                type="button"
                aria-label={`Remove “${FILTER_LABELS[key](state, named)}”`}
                onClick={(e) => remove(key, e.currentTarget)}
                className="relative hit-area grid h-full shrink-0 place-items-center rounded-r-md px-1.5 text-muted-foreground transition-colors duration-(--duration-fast) hover:bg-accent hover:text-foreground"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </m.li>
          );
        })}
      </AnimatePresence>
    </ul>
  );
}

function Empty({ state, set, filters, named }: { state: FeedState; set: (next: Partial<FeedState>) => void; filters: (keyof Filters)[]; named: Named }) {
  const box = "rounded-xl border border-border bg-card shadow-card";
  if (filters.length === 0)
    return (
      <section className={box}>
        <EmptyState
          icon={Compass}
          headingLevel="h2"
          title="No products collected yet"
          action={
            <Button asChild variant="secondary">
              <Link href="/admin/data-health">Open Data Health</Link>
            </Button>
          }
        >
          Collectors run nightly on the collector host. Products appear here once a source has matched them.
        </EmptyState>
      </section>
    );
  return (
    <section className={box}>
      <EmptyState
        icon={SearchX}
        headingLevel="h2"
        title={filters.length === 1 ? "No products match this filter" : `No products match ${filters.length} filters`}
        action={
          <>
            {filters.map((key) => (
              <Button key={key} size="sm" onClick={() => set({ [key]: null })}>
                <X aria-hidden />
                Remove “{FILTER_LABELS[key](state, named)}”
              </Button>
            ))}
            {filters.length > 1 && (
              <Button size="sm" variant="ghost" onClick={() => set(NO_FILTERS)}>
                Clear filters
              </Button>
            )}
          </>
        }
      >
        Remove a filter to widen the feed. Sort and view stay as they are.
      </EmptyState>
    </section>
  );
}

const SAID = { blocked: "blocked", disabled: "paused", stale: "stale" } as const;

/** A source feeding the feed is blocked, paused or stale: the numbers it feeds may be out of date (UI States, Partial). */
function DegradedBanner({ degraded }: { degraded: components["schemas"]["Degraded"][] }) {
  return (
    <p className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
      <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
      {degraded.map((d, i) => (
        <span key={d.source}>
          {i > 0 && "; "}
          <span className="font-medium">
            {d.source_name} {SAID[d.state]}
          </span>
          {d.since && (
            <>
              {d.state === "stale" ? ", last captured " : " since "}
              <time dateTime={d.since}>{formatUtc(d.since)}</time>
            </>
          )}
        </span>
      ))}
      . Counts, prices and velocity from {degraded.length === 1 ? "it" : "them"} may be out of date.{" "}
      <Link href="/admin/data-health" className="link-inline rounded-sm whitespace-nowrap underline decoration-border-strong underline-offset-2 hover:decoration-current">
        Open Data Health
      </Link>
    </p>
  );
}
