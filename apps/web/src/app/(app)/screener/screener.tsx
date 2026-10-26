"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { DropdownMenu } from "radix-ui";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, Check, Columns3, Compass, SearchX, SlidersHorizontal, X } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { $api, isProblem } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { Toast, useNote } from "../boards/parts";
import { count, ProductTable, TableSkeleton } from "../discover/feed-views";
import { joinPages } from "../discover/url-state";
import { RowCard, scoreStale, tableColumns, type Row } from "./cells";
import { Conditions, describe, menu, menuItem, without } from "./conditions";
import { clean, COLUMNS, conditionsOf, decode, DEFAULT, DEFAULT_COLUMNS, same, screenSearch, SORTS, type Column, type Definition, type SortKey } from "./definition";
import { ScreensBar, type Go } from "./screens";

const UUID = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
const retry = (failures: number, error: unknown) => !(isProblem(error) && error.status < 500) && failures < 1;
const control =
  "h-(--button-h-md) min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) hover:border-border-strong";
const box = "rounded-xl border border-border bg-card shadow-card";
const dayOf = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
type Edit = (next: Partial<Definition> | ((d: Definition) => Partial<Definition>)) => void;

// WF-1b (vault Features/Product Screener, DEC-347): a condition builder over GET /v1/screener's filters, a sort, the
// shared product table and saved screens. The URL holds the screen: `?screen=` a saved one and `?q=` the definition
// while it differs from that (base64url JSON), so an unsaved screen can be bookmarked. Edits replace the URL entry,
// opening a screen pushes one (DEC-238 e).
export function Screener() {
  const params = useSearchParams();
  const ready = useApiReady();
  const screenId = UUID.test(params.get("screen") ?? "") ? params.get("screen") : null;
  const draft = decode(params.get("q"));
  const saved = $api.useQuery("get", "/v1/screens/{screen_id}", { params: { path: { screen_id: screenId ?? "" } } }, { enabled: ready && !!screenId, retry });
  const stored = saved.data ? clean(saved.data) : null;
  const definition = draft ?? stored ?? DEFAULT;
  const dirty = !!stored && !!draft && !same(draft, stored);
  const waiting = !!screenId && !draft && !stored;
  const [note, setNote] = useNote();
  const [adding, setAdding] = useState(false);
  const [sheet, setSheet] = useState(false);

  const go: Go = useCallback((screen, next, push = false) => {
    const search = screenSearch(screen, next);
    window.history[push ? "pushState" : "replaceState"](null, "", search ? `?${search}` : window.location.pathname);
  }, []);
  // From the URL at call time, not this render's definition, so quick edits build on each other (as Discover's set).
  const edit: Edit = (next) => {
    const current = decode(new URLSearchParams(window.location.search).get("q")) ?? stored ?? DEFAULT;
    const d = { ...current, ...(typeof next === "function" ? next(current) : next) };
    go(screenId, same(d, stored ?? DEFAULT) ? null : d);
  };

  // F adds a filter (vault UX spec, Keyboard); below md the builder is in the sheet, so it doesn't.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "f" || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target) || !matchMedia("(min-width: 48rem)").matches) return;
      if (document.querySelector('[role="dialog"], [role="menu"]')) return;
      e.preventDefault();
      setAdding(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = $api.useInfiniteQuery(
    "get",
    "/v1/screener",
    { params: { query: { filters: JSON.stringify(definition.filters), sort: definition.sort, order: definition.order } } },
    {
      enabled: ready && !waiting,
      pageParamName: "cursor",
      initialPageParam: null, // not undefined, which openapi-react-query sends as cursor=0 (DEC-166)
      getNextPageParam: (page) => page.next_cursor,
      retry,
    },
  );
  const rows: Row[] = joinPages(results.data?.pages);
  const first = results.data?.pages[0];
  const now = results.dataUpdatedAt;
  const columns = definition.columns ?? DEFAULT_COLUMNS;
  const given = conditionsOf(definition.filters);
  const newest = rows.reduce<string | null>((max, r) => ("day" in r.trend && (!max || r.trend.day > max) ? r.trend.day : max), null);
  const conditions = <Conditions key={screenId} filters={definition.filters} set={(update) => edit((d) => ({ filters: update(d.filters) }))} open={adding} onOpenChange={setAdding} />;

  return (
    <div className="flex flex-col gap-4">
      <ScreensBar screenId={screenId} stored={saved.data} definition={definition} dirty={dirty} go={go} setNote={setNote} />
      {waiting && saved.isError ? (
        <section className={box}>
          <PanelError headingLevel="h2" size="md" title="Couldn't open this saved screen" error={saved.error} retry={() => void saved.refetch()} />
        </section>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <section aria-label="Filters" className={cn(box, "p-3 max-md:hidden")}>
            {waiting ? <span className="text-label text-subtle-foreground">Opening the screen…</span> : conditions}
          </section>
          <div className="flex min-w-0 flex-col gap-3">
            {/* After the conditions in the tab order: build, then sort, then the rows. */}
            <div className="flex flex-wrap items-center gap-2">
              <Button className="md:hidden" onClick={() => setSheet(true)}>
                <SlidersHorizontal aria-hidden />
                Filters{given.length > 0 && ` (${given.length})`}
              </Button>
              <SortPicker definition={definition} edit={edit} />
              <ColumnPicker columns={columns} edit={edit} />
            </div>
            <p className="text-label text-subtle-foreground" aria-live="polite">
              {first ? (
                <>
                  {count(rows.length)} {rows.length === 1 ? "product" : "products"}
                  {results.hasNextPage && " loaded, more below"}
                  {newest && (
                    <>
                      {" · "}
                      {scoreStale(newest, now) && <span aria-hidden className="mr-1 inline-block size-1.5 rounded-full bg-warning align-middle" />}
                      <span className={cn(scoreStale(newest, now) && "text-foreground")}>
                        {scoreStale(newest, now) ? "nothing scored since " : "scores as of "}
                        <time dateTime={newest}>{dayOf.format(new Date(newest))}</time>
                      </span>
                    </>
                  )}
                  {Object.keys(first.unapplied).length > 0 && " · risk isn't applied until Phase 5"}
                </>
              ) : (
                "…"
              )}
            </p>
            {results.data && results.isRefetchError && <StaleLine boxed what="Couldn't refresh the results" error={results.error} asOf={now} retry={() => void results.refetch()} />}
            {!results.data ? (
              results.isError ? (
                <section className={box}>
                  <PanelError headingLevel="h2" size="md" title="Couldn't run this screen" error={results.error} retry={() => void results.refetch()} />
                </section>
              ) : (
                <>
                  <span className="sr-only" role="status">
                    Running the screen…
                  </span>
                  <TableSkeleton columns={columns.map((c) => COLUMNS[c])} />
                </>
              )
            ) : rows.length === 0 ? (
              <Empty definition={definition} edit={edit} />
            ) : (
              <>
                <div className="max-md:hidden">
                  <ProductTable items={rows} columns={tableColumns(columns, now)} loadingMore={results.isFetchingNextPage} />
                </div>
                <ul aria-label="Products" className="flex flex-col gap-2 md:hidden">
                  {rows.map((row) => (
                    <li key={row.id}>
                      <RowCard row={row} columns={columns} now={now} />
                    </li>
                  ))}
                </ul>
                <LoadMore
                  note={`${count(rows.length)} ${rows.length === 1 ? "product" : "products"}${results.hasNextPage ? "" : ", all of them"}`}
                  label="Load more"
                  more={!!results.hasNextPage}
                  pending={results.isFetchingNextPage}
                  error={results.isFetchNextPageError ? results.error : null}
                  errorTitle="Couldn't load more products"
                  onLoad={() => void results.fetchNextPage()}
                />
              </>
            )}
          </div>
        </div>
      )}
      <Sheet open={sheet} onOpenChange={setSheet}>
        <SheetContent side="bottom" closeLabel="Close filters" className="max-h-[85dvh] gap-4 px-4 pt-4 pb-4 md:hidden">
          <SheetTitle className="text-title-3 font-semibold">Filters</SheetTitle>
          <SheetDescription className="sr-only">Results update as you change a condition.</SheetDescription>
          <div className="overflow-y-auto">{conditions}</div>
          <Button variant="primary" onClick={() => setSheet(false)}>
            Show results
          </Button>
        </SheetContent>
      </Sheet>
      <Toast note={note} />
    </div>
  );
}

function SortPicker({ definition, edit }: { definition: Definition; edit: Edit }) {
  const desc = definition.order === "desc";
  return (
    <div className="flex items-center gap-1">
      <label className="flex items-center gap-2">
        <span aria-hidden className="text-label text-muted-foreground max-sm:hidden">
          Sort
        </span>
        <select aria-label="Sort" className={control} value={definition.sort} onChange={(e) => edit({ sort: e.target.value as SortKey })}>
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {COLUMNS[s]}
            </option>
          ))}
        </select>
      </label>
      <Button
        size="icon"
        variant="secondary"
        aria-label={desc ? "Order: highest first" : "Order: lowest first"}
        title={`${desc ? "Highest" : "Lowest"} first; missing values always last`}
        onClick={() => edit((d) => ({ order: d.order === "desc" ? "asc" : "desc" }))}
      >
        {desc ? <ArrowDownWideNarrow aria-hidden /> : <ArrowUpNarrowWide aria-hidden />}
      </Button>
    </div>
  );
}

/** The table's metric columns, saved with the screen (DEC-347); the phone rows show the first three. */
function ColumnPicker({ columns, edit }: { columns: Column[]; edit: Edit }) {
  const all = Object.keys(COLUMNS) as Column[];
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button variant="secondary">
          <Columns3 aria-hidden />
          <span className="max-sm:sr-only">Columns</span>
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className={menu}>
          {all.map((c) => (
            <DropdownMenu.CheckboxItem
              key={c}
              className={menuItem}
              checked={columns.includes(c)}
              disabled={columns.length === 1 && columns.includes(c)}
              onSelect={(e) => e.preventDefault()} // the menu stays open for the next one
              onCheckedChange={(on) => {
                const next = all.filter((k) => (k === c ? on : columns.includes(k)));
                edit({ columns: next.join() === DEFAULT_COLUMNS.join() ? null : next });
              }}
            >
              <span className="grid size-3.5 place-items-center">
                <DropdownMenu.ItemIndicator>
                  <Check className="size-3.5" aria-hidden />
                </DropdownMenu.ItemIndicator>
              </span>
              {COLUMNS[c]}
            </DropdownMenu.CheckboxItem>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Empty({ definition, edit }: { definition: Definition; edit: Edit }) {
  const given = conditionsOf(definition.filters);
  if (given.length === 0)
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
        title="No products match"
        action={given.map((key) => (
          <Button key={key} size="sm" onClick={() => edit((d) => ({ filters: without(d.filters, key) }))}>
            <X aria-hidden />
            Remove “{describe(key, definition.filters)}”
          </Button>
        ))}
      >
        Remove a condition to widen the screen. A product missing a metric never passes its condition.
      </EmptyState>
    </section>
  );
}
