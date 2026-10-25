"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { keepPreviousData } from "@tanstack/react-query";
import { Check, ChevronRight, CircleHelp, CircleSlash, PauseCircle, SearchX, Store } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Ago, PanelError, Pill, StaleLine, TapTooltip } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { EmptyState } from "@/components/pulso/empty-state";
import { Metric } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { apiQuery, day, FILTERS, filterSearch, money, nextFilter, original, parseFilter, UNKNOWN, type Filter, type Page, type Row } from "./model";
import { Summary, SummarySkeleton } from "./summary";

const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
const COLUMNS = ["Store", "Price", "Started", "Still listed", "Running ads", "Last seen"];
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";
// Native history, like the tab bar: Next syncs useSearchParams without a server round trip.
function setFilter(next: Filter) {
  const query = filterSearch(window.location.search, next);
  window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
}

const link = "link-inline rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current";

// UX-7 (vault Features/Product Page - Sellers): summary strip, filter chips kept in the URL, a dense table and, below
// 768 px, seller cards with delisted sellers collapsed. Rows never animate (Motion System rule 2).
export function SellersTab({ id }: { id: string }) {
  const filter = parseFilter(useSearchParams());
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "f" || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      e.preventDefault();
      setFilter(nextFilter(parseFilter(new URLSearchParams(window.location.search)))); // the URL, ahead of a re-render
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const sellers = $api.useInfiniteQuery(
    "get",
    "/v1/products/{product_id}/sellers",
    { params: { path: { product_id: id }, query: apiQuery(filter) } },
    {
      enabled: useApiReady(),
      pageParamName: "cursor",
      initialPageParam: null, // null, not undefined (DEC-166)
      getNextPageParam: (page) => page.next_cursor,
      placeholderData: keepPreviousData, // a chip keeps the summary in place while its rows load
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  const { data, error, hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = sellers;
  const first = data?.pages[0];
  const rows = data?.pages.flatMap((p) => p.rows) ?? [];
  const now = sellers.dataUpdatedAt;
  const retry = () => void sellers.refetch();

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="sr-only">Sellers</h2>
      {first && first.crawler.status !== "enabled" && <CrawlerBanner page={first} />}
      {data && sellers.isRefetchError && !isFetchNextPageError && <StaleLine boxed what="Couldn't refresh sellers" error={error} asOf={now} retry={retry} />}
      {!data && sellers.isError ? (
        <PanelError headingLevel="h2" size="md" title="Couldn't load sellers" error={error} retry={retry} />
      ) : (
        <>
          {first ? <Summary page={first} now={now} /> : <SummarySkeleton />}
          <Chips filter={filter} />
          {first && first.as_of === null ? (
            <EmptyState
              icon={Store}
              title="No stores seen selling this yet"
              action={
                <Button asChild variant="secondary">
                  <Link href="/admin/data-health">Import a CSV in Data Health</Link>
                </Button>
              }
            >
              Pulso only sees the stores it tracks (the seed list). When a tracked store lists this product, it shows here with its price and start date.
            </EmptyState>
          ) : first && rows.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title={`No sellers match “${FILTERS[filter]}”`}
              action={
                <Button variant="secondary" onClick={() => setFilter(filter === "all" ? "active" : "all")}>
                  {filter === "all" ? "Show active sellers" : "Include delisted sellers"}
                </Button>
              }
            />
          ) : (
            <>
              <p className="text-label text-subtle-foreground" aria-live="polite">
                {first ? (
                  <>
                    {rows.length} {rows.length === 1 ? "seller" : "sellers"}
                    {hasNextPage && " loaded"} · active first, newest start first · as of{" "}
                    {first.as_of && <time dateTime={first.as_of}>{formatUtc(first.as_of)}</time>}
                  </>
                ) : (
                  " "
                )}
              </p>
              <SellerTable rows={first ? rows : null} now={now} />
              {first && <SellerCards rows={rows} now={now} />}
              {first && (first.spread.untrackable > 0 || first.spread.missing > 0) && <Footnote page={first} />}
              {(hasNextPage || isFetchNextPageError) && (
                <LoadMore
                  note={`${rows.length} sellers shown`}
                  label="Load more sellers"
                  more={!!hasNextPage}
                  pending={isFetchingNextPage}
                  error={isFetchNextPageError ? error : null}
                  errorTitle="Couldn't load more sellers"
                  onLoad={() => void fetchNextPage()}
                />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

const reasonText = (reason: string) => reason.replace(/^consecutive_blocks:/, "repeated blocks, ").replace(/http_(\d+)/g, "HTTP $1");

/** The Shopify store crawler is off (owner decision 2, vault Source - Shopify Stores): prices and dates may be old. */
function CrawlerBanner({ page }: { page: Page }) {
  const { status, since, reason } = page.crawler;
  return (
    <p role="status" className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
      <PauseCircle className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
      <span className="font-medium">{status === "auto_disabled" ? "Store crawler stopped itself" : "Store crawler paused"}</span>
      {since && (
        <>
          {" "}
          since <time dateTime={since}>{formatUtc(since)}</time>
        </>
      )}
      {reason && ` (${reasonText(reason)})`}. Seller data as of {page.as_of ? <time dateTime={page.as_of}>{formatUtc(page.as_of)}</time> : "never"};
      a listing whose store&apos;s last crawl didn&apos;t finish shows Unknown.{" "}
      <Link href="/admin/data-health" className={cn(link, "whitespace-nowrap")}>
        Import a CSV in Data Health
      </Link>
    </p>
  );
}

function Chips({ filter }: { filter: Filter }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label="Show sellers, F cycles" className="flex flex-wrap gap-1.5">
        {(Object.keys(FILTERS) as Filter[]).map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
            className={cn(
              "relative hit-area h-(--button-h-sm) rounded-md border px-2.5 text-label font-medium whitespace-nowrap",
              filter === f ? "border-brand/50 bg-brand-muted text-foreground" : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
            )}
          >
            {FILTERS[f]}
          </button>
        ))}
      </div>
      <span className="text-micro text-subtle-foreground max-md:hidden" aria-hidden>
        <Kbd>F</Kbd> cycles · <Kbd>J</Kbd> <Kbd>K</Kbd> move · <Kbd>O</Kbd> opens the store
      </span>
    </div>
  );
}

function Price({ row, now }: { row: Row; now: number }) {
  const from = row.price_max_minor !== null && row.price_minor !== null && row.price_max_minor > row.price_minor;
  if (row.price_usd_minor === null || row.as_of === null) {
    if (row.price_minor === null || row.currency === null) return <span className="text-subtle-foreground" title="No price captured yet">—</span>;
    return (
      <span className="text-muted-foreground" title={`No ${row.currency}→USD rate for ${row.as_of ? day.format(new Date(row.as_of)) : "its date"}, so this seller is left out of the spread. Pulso never guesses a rate.`}>
        {original(row.price_minor, row.currency)} <span className="text-micro text-subtle-foreground">no USD rate</span>
      </span>
    );
  }
  const converted = row.currency !== "USD" && row.price_minor !== null && row.currency !== null;
  const label = converted ? `Price, ${original(row.price_minor!, row.currency!)} at the ${day.format(new Date(row.as_of))} rate` : "Price";
  const stat = { value: row.price_usd_minor, source: "shopify_stores", source_name: row.source_name, as_of: row.as_of, raw_payload_id: row.raw_payload_id, method: null, stale: row.stale };
  return (
    <span className="whitespace-nowrap">
      {from && <span className="mr-1 text-micro text-subtle-foreground">from</span>}
      <Metric stat={stat} label={label} format={money} now={now} className={cn(row.stale && "text-muted-foreground")} />
      {converted && <span className="ml-1 text-micro text-subtle-foreground">{row.currency}</span>}
    </span>
  );
}

function Started({ row }: { row: Row }) {
  const store = row.started_basis === "store";
  return (
    <span className="whitespace-nowrap" title={store ? "The store's own product date" : "First seen by Pulso: the store gave no date"}>
      <time dateTime={row.started_at}>{day.format(new Date(row.started_at))}</time>
      <span className="ml-1.5 text-micro text-subtle-foreground">{store ? "store date" : "first seen"}</span>
    </span>
  );
}

function Listed({ row }: { row: Row }) {
  if (row.listed === "listed")
    return (
      <span className="inline-flex items-center gap-1 text-foreground">
        <Check className="size-3.5 text-muted-foreground" aria-hidden />
        Listed
      </span>
    );
  if (row.listed === "delisted" && row.delisted_at)
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground" title={`A complete crawl omitted it on ${formatUtc(row.delisted_at)}`}>
        <CircleSlash className="size-3.5" aria-hidden />
        Delisted <time dateTime={row.delisted_at}>{day.format(new Date(row.delisted_at))}</time>
      </span>
    );
  return (
    <TapTooltip hint={UNKNOWN[row.unknown_reason ?? "never_crawled"]} side="top" contentClassName="max-w-64" type="button" className="relative hit-area inline-flex cursor-help items-center gap-1 rounded-sm text-muted-foreground">
      <CircleHelp className="size-3.5" aria-hidden />
      Unknown
    </TapTooltip>
  );
}

function LastSeen({ row, now }: { row: Row; now: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-subtle-foreground">
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", row.stale ? "bg-warning" : "bg-border-strong")} />
      <Ago iso={row.last_seen} now={now} source={row.source_name} />
      {row.stale && <span className="text-warning">· stale</span>}
    </span>
  );
}

function StoreName({ row }: { row: Row }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <a href={row.url} target="_blank" rel="noopener noreferrer" title={`Open the product on ${row.domain}`} className="truncate rounded-sm font-medium text-foreground hover:underline">
        {row.domain}
      </a>
      {row.tracked && (
        <Pill tone="neutral" icon={Check}>
          Tracked
        </Pill>
      )}
      {row.untrackable && (
        <span title="Headless or password-protected: left out of the spread">
          <Pill tone="muted" icon={CircleSlash}>
            Untrackable
          </Pill>
        </span>
      )}
    </span>
  );
}

/** j/k or arrows move between rows, Enter or o opens the listing on the store (vault Product Page - Sellers, Keyboard).
 *  Inner controls keep their own keys. ponytail: no Store Spy page until Phase 3, so Enter and o both open the store. */
function onRowKey(e: React.KeyboardEvent<HTMLElement>, url: string) {
  if (e.target !== e.currentTarget) return;
  const go = (el: Element | null) => el instanceof HTMLElement && (e.preventDefault(), el.focus());
  if (e.key === "j" || e.key === "ArrowDown") go(e.currentTarget.nextElementSibling);
  else if (e.key === "k" || e.key === "ArrowUp") go(e.currentTarget.previousElementSibling);
  else if (e.key === "Enter" || e.key.toLowerCase() === "o") {
    e.preventDefault();
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

function SellerTable({ rows, now }: { rows: Row[] | null; now: number }) {
  return (
    <div role="region" aria-label="Sellers" tabIndex={0} className="relative max-h-[max(24rem,calc(100dvh-20rem))] overflow-auto overscroll-contain rounded-lg border border-border max-md:hidden">
      <table className="w-full min-w-200 border-separate border-spacing-0 zone-data">
        <thead className="sticky top-0 z-20 bg-card">
          <tr className="row-h text-label text-muted-foreground">
            {COLUMNS.map((name, i) => (
              <th key={name} scope="col" className={cn(cell, "border-border bg-card font-medium", i === 1 || i === 2 ? "text-right" : "text-left")}>
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows
            ? rows.map((row, i) => (
                <tr
                  key={row.listing_id}
                  tabIndex={i === 0 ? 0 : -1}
                  aria-label={`${row.domain}, ${row.listed}`}
                  onKeyDown={(e) => onRowKey(e, row.url)}
                  className="row-h outline-ring -outline-offset-2 hover:bg-(--table-row-hover) focus-visible:outline-2"
                >
                  <th scope="row" className={cn(cell, "max-w-80 text-left font-normal")}>
                    <StoreName row={row} />
                  </th>
                  <td className={cn(cell, "num")}>
                    <Price row={row} now={now} />
                  </td>
                  <td className={cn(cell, "num")}>
                    <Started row={row} />
                  </td>
                  <td className={cell}>
                    <Listed row={row} />
                  </td>
                  <td className={cell}>
                    <span className="text-subtle-foreground" title={row.running_ads.reason}>
                      No source yet
                    </span>
                  </td>
                  <td className={cell}>
                    <LastSeen row={row} now={now} />
                  </td>
                </tr>
              ))
            : Array.from({ length: 6 }, (_, i) => (
                <tr key={i} aria-hidden className="row-h">
                  {COLUMNS.map((name, c) => (
                    <td key={name} className={cell}>
                      <Skeleton className={cn("h-3.5", c === 0 ? "w-40" : "w-16", (c === 1 || c === 2) && "ml-auto")} />
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}

function SellerCard({ row, now }: { row: Row; now: number }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border border-border-subtle p-3 zone-data">
      <div className="flex items-start justify-between gap-3">
        <StoreName row={row} />
        <span className="shrink-0 tabular-nums">
          <Price row={row} now={now} />
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-label text-muted-foreground">
        <Started row={row} />
        <Listed row={row} />
        <LastSeen row={row} now={now} />
      </div>
    </li>
  );
}

/** Below 768 px each seller is a card; delisted ones fold into a "Delisted (n)" group (UX spec, Responsive). */
function SellerCards({ rows, now }: { rows: Row[]; now: number }) {
  const active = rows.filter((r) => r.listed !== "delisted");
  const delisted = rows.filter((r) => r.listed === "delisted");
  return (
    <div className="flex flex-col gap-2 md:hidden">
      <ul aria-label="Sellers" className="flex flex-col gap-2">
        {active.map((row) => (
          <SellerCard key={row.listing_id} row={row} now={now} />
        ))}
      </ul>
      {delisted.length > 0 && (
        <details className="group rounded-lg border border-border-subtle">
          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-lg px-3 text-label font-medium text-muted-foreground">
            <ChevronRight className="size-4 group-open:rotate-90" aria-hidden />
            Delisted ({delisted.length})
          </summary>
          <ul className="flex flex-col gap-2 px-2 pb-2">
            {delisted.map((row) => (
              <SellerCard key={row.listing_id} row={row} now={now} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Footnote({ page }: { page: Page }) {
  return (
    <p className="text-micro text-subtle-foreground">
      The price spread leaves out {page.spread.untrackable > 0 && "untrackable stores (headless or password-protected)"}
      {page.spread.untrackable > 0 && page.spread.missing > 0 && " and "}
      {page.spread.missing > 0 && "sellers without a USD price: no capture yet, or no FX rate for the snapshot's date, which Pulso never guesses"}.
    </p>
  );
}
