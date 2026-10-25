"use client";

import { useCallback } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { keepPreviousData } from "@tanstack/react-query";
import { Download, SearchX, TriangleAlert, Trophy, Unplug } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Missing, PanelError, StaleLine } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { groupRows, KINDS, type Kind } from "./model";

type Page = components["schemas"]["AmazonRankPage"];
type Row = components["schemas"]["AmazonRankRow"];
type SetParams = (next: Record<string, string | null>) => void;

const IMPORT = "/admin/data-health#import";
const TEMPLATE = "/api/v1/admin/sources/amazon/import/template";
const LABEL = "Amazon · manual import"; // vault Methodology & Confidence: Amazon data says how it arrived
const DAY = 86_400_000;
const date = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const day = (iso: string) => date.format(new Date(iso));
const count = (n: number) => n.toLocaleString("en-US");
const box = "rounded-xl border border-border bg-card shadow-card";
const control =
  "h-(--button-h-md) min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) hover:border-border-strong";
const link = "link-inline rounded-sm whitespace-nowrap underline decoration-border-strong underline-offset-2 hover:decoration-current";
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";
// Rank, price, rating and reviews are numbers: right-aligned and tabular (vault Design/Tables & Data Density).
const COLUMNS = [
  ["Rank", "num w-14"],
  ["Product", "text-left"],
  ["ASIN", "text-left"],
  ["Price", "num"],
  ["Rating", "num"],
  ["Reviews", "num"],
] as const;

// AMZ-1b (DEC-286): every imported list (category × Best Sellers or Movers & Shakers) at its newest day, one group per
// list so ranks never mix. The URL holds the category and list filters; replacing it keeps Back, like Google popular.
export function AmazonRanks() {
  const params = useSearchParams();
  const category = params.get("category");
  const kind = params.get("kind");
  const rankKind = kind === "bsr" || kind === "movers" ? kind : null;
  const set = useCallback<SetParams>((next) => {
    const search = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(next)) {
      if (value === null) search.delete(key);
      else search.set(key, value);
    }
    const text = search.toString();
    window.history.replaceState(null, "", text ? `?${text}` : window.location.pathname);
  }, []);
  const query = $api.useInfiniteQuery(
    "get",
    "/v1/amazon/ranks",
    { params: { query: { category: category ?? undefined, rank_kind: rankKind ?? undefined } } },
    {
      enabled: useApiReady(),
      pageParamName: "cursor",
      initialPageParam: null, // null, not undefined (DEC-166)
      getNextPageParam: (page) => page.next_cursor,
      placeholderData: keepPreviousData, // the toolbar keeps focus while new lists load
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  const { data, error } = query;
  if (!data)
    return query.isError ? (
      <section className={box}>
        <PanelError headingLevel="h2" size="md" title="Couldn't load Amazon ranks" error={error} retry={() => void query.refetch()} />
      </section>
    ) : (
      <Loading />
    );
  const page = data.pages[0];
  if (page.source === null) return <NoSource />;
  if (page.lists.length === 0) return <NoImport />;
  const rows = data.pages.flatMap((p) => p.rows);
  const lists = page.lists.filter((l) => (category ?? l.category) === l.category && (rankKind ?? l.rank_kind) === l.rank_kind).length;
  return (
    <div className="flex flex-col gap-4">
      <Toolbar page={page} category={category} kind={rankKind} set={set} />
      {page.as_of && (
        <p className="text-label text-subtle-foreground" aria-live="polite">
          <span className="font-medium text-muted-foreground">{LABEL}</span>, as of{" "}
          <time dateTime={page.as_of} title={page.captured_at ? `Imported ${formatUtc(page.captured_at)}` : undefined}>
            {day(page.as_of)}
          </time>{" "}
          · {count(page.total)} {page.total === 1 ? "rank" : "ranks"} in {lists} {lists === 1 ? "list" : "lists"}
        </p>
      )}
      {page.stale && page.as_of && (
        <p className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
          <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
          <span className="font-medium">
            The newest Amazon ranks here are from {day(page.as_of)}, {Math.floor((query.dataUpdatedAt - Date.parse(page.as_of)) / DAY)} days ago.
          </span>{" "}
          Ranks move daily: import a fresh file.{" "}
          <Link href={IMPORT} className={link}>
            Open CSV import
          </Link>
        </p>
      )}
      {query.isRefetchError && <StaleLine boxed what="Couldn't refresh Amazon ranks" error={error} asOf={query.dataUpdatedAt} retry={() => void query.refetch()} />}
      {rows.length === 0 ? (
        <NoRows set={set} />
      ) : (
        <>
          <Table rows={rows} page={page} />
          <LoadMore
            note={`${count(rows.length)} of ${count(page.total)} loaded`}
            label="Load more"
            more={query.hasNextPage}
            pending={query.isFetchingNextPage}
            error={query.isFetchNextPageError ? error : null}
            errorTitle="Couldn't load more ranks"
            onLoad={() => void query.fetchNextPage()}
          />
        </>
      )}
    </div>
  );
}

/** A visible label beside its control, which names itself (a wrapping label would add the selected option). */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 items-center gap-2">
      <span aria-hidden className="text-label text-muted-foreground">
        {label}
      </span>
      {children}
    </label>
  );
}

function Toolbar({ page, category, kind, set }: { page: Page; category: string | null; kind: Kind | null; set: SetParams }) {
  const categories = [...new Set(page.lists.map((l) => l.category))];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Field label="Category">
        <select aria-label="Category" className={cn(control, "max-w-64")} value={category ?? ""} onChange={(e) => set({ category: e.target.value || null })}>
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
          {category && !categories.includes(category) && <option value={category}>{category}</option>}
        </select>
      </Field>
      <Field label="List">
        <select aria-label="List" className={control} value={kind ?? ""} onChange={(e) => set({ kind: e.target.value || null })}>
          <option value="">All lists</option>
          {Object.entries(KINDS).map(([k, name]) => (
            <option key={k} value={k}>
              {name}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
}

function Price({ row }: { row: Row }) {
  if (row.price_minor == null) return <Missing reason="No price in the import" />;
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: row.currency });
  return <>{money.format(row.price_minor / 10 ** (money.resolvedOptions().maximumFractionDigits ?? 2))}</>;
}

// Dense table: sticky header, tabular numbers, one body per list headed by its category, list and day. Rows never
// animate (Motion System rule 2). A row whose GTIN reaches a live product links to it; the rest still show (DEC-267 c).
function Table({ rows, page }: { rows: Row[]; page: Page }) {
  const sizes = new Map(page.lists.map((l) => [`${l.category}\n${l.rank_kind}`, l.rows]));
  return (
    <div role="region" aria-label="Amazon ranks" tabIndex={0} className={cn(box, "relative max-h-[max(24rem,calc(100dvh-18rem))] overflow-auto overscroll-contain")}>
      <table className="w-full border-separate border-spacing-0 zone-data">
        <thead className="sticky top-0 z-20 bg-card">
          <tr className="row-h text-label text-muted-foreground">
            {COLUMNS.map(([name, align]) => (
              <th key={name} scope="col" className={cn(cell, "border-border bg-card font-medium", align)}>
                {name}
              </th>
            ))}
          </tr>
        </thead>
        {groupRows(rows).map(({ category, kind, rows: ranked }) => {
          const [first, key] = [ranked[0], `${category}\n${kind}`];
          const source = `${LABEL} · as of ${day(first.as_of)} · imported ${formatUtc(first.captured_at)}`;
          const size = sizes.get(key) ?? ranked.length;
          return (
            <tbody key={key}>
              <tr className="row-h">
                <th scope="colgroup" colSpan={COLUMNS.length} className={cn(cell, "border-border bg-secondary text-left text-label font-medium text-foreground")}>
                  {category} › {KINDS[kind]}{" "}
                  <span className="ml-1 font-normal text-muted-foreground tabular-nums">
                    as of{" "}
                    <time dateTime={first.as_of} title={`Imported ${formatUtc(first.captured_at)}`}>
                      {day(first.as_of)}
                    </time>{" "}
                    · {count(size)} {size === 1 ? "rank" : "ranks"}
                  </span>
                </th>
              </tr>
              {ranked.map((row) => (
                <tr key={row.asin} className="row-h hover:bg-(--table-row-hover)">
                  <td className={cn(cell, "num text-muted-foreground")} title={source}>
                    {count(row.rank)}
                  </td>
                  <th scope="row" className={cn(cell, "max-w-104 text-left font-normal")}>
                    {row.product_id ? (
                      <Link href={`/products/${row.product_id}`} title={`${row.title} · open in Pulso`} className="block truncate rounded-sm font-medium text-foreground hover:underline">
                        {row.title}
                      </Link>
                    ) : (
                      <span title={`${row.title} · no Pulso product shares its GTIN yet`} className="block truncate text-foreground">
                        {row.title}
                      </span>
                    )}
                  </th>
                  <td className={cn(cell, "font-mono text-muted-foreground")}>{row.asin}</td>
                  <td className={cn(cell, "num")} title={source}>
                    <Price row={row} />
                  </td>
                  <td className={cn(cell, "num")} title={source}>
                    {row.rating == null ? <Missing reason="No rating in the import" /> : row.rating.toLocaleString("en-US", { minimumFractionDigits: 1 })}
                  </td>
                  <td className={cn(cell, "num")} title={source}>
                    {row.review_count == null ? <Missing reason="No review count in the import" /> : count(row.review_count)}
                  </td>
                </tr>
              ))}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}

function NoRows({ set }: { set: SetParams }) {
  return (
    <section className={box}>
      <EmptyState icon={SearchX} headingLevel="h2" title="No Amazon list matches" action={<Button onClick={() => set({ category: null, kind: null })}>Show every list</Button>}>
        No import has this category and list. Pick another, or import it in Data Health › CSV import.
      </EmptyState>
    </section>
  );
}

function NoImport() {
  return (
    <section className={box}>
      <EmptyState
        icon={Trophy}
        headingLevel="h2"
        title="No Amazon import yet"
        action={
          <>
            <Button asChild variant="secondary">
              <Link href={IMPORT}>Open CSV import</Link>
            </Button>
            <Button asChild variant="ghost">
              <a href={TEMPLATE} download="amazon-template.csv">
                <Download aria-hidden />
                Download template
              </a>
            </Button>
          </>
        }
      >
        Export Best Sellers or Movers &amp; Shakers ranks from a tool whose terms allow it, or list them by hand, then import the file in Data Health as
        “Amazon”. Never a scrape.
      </EmptyState>
    </section>
  );
}

function NoSource() {
  return (
    <section className={box}>
      <EmptyState
        icon={Unplug}
        headingLevel="h2"
        title="Amazon: no source yet"
        action={
          <Button asChild variant="secondary">
            <Link href="/admin/data-health">Open Data Health</Link>
          </Button>
        }
      >
        This database has no Amazon source, so there is nothing to import into yet. Pulso&apos;s database update adds it; Data Health lists it once it&apos;s
        there.
      </EmptyState>
    </section>
  );
}

function Loading() {
  return (
    <>
      {/* The skeleton is aria-hidden, so the first load says so to a screen reader (p2-30). */}
      <span className="sr-only" role="status">
        Loading Amazon ranks…
      </span>
      <div aria-hidden className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          <Skeleton className="h-(--button-h-md) w-60" />
          <Skeleton className="h-(--button-h-md) w-44" />
        </div>
        <Skeleton className="h-3.5 w-96 max-w-full" />
        <div className={cn(box, "overflow-hidden")}>
          <table className="w-full border-separate border-spacing-0">
            <tbody>
              {Array.from({ length: 12 }, (_, i) => (
                <tr key={i} className="row-h">
                  {COLUMNS.map(([name, align]) => (
                    <td key={name} className={cell}>
                      <Skeleton className={cn("h-3.5", name === "Product" ? "w-64 max-md:w-32" : "w-12", align.startsWith("num") && "ml-auto")} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
