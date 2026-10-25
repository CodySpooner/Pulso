"use client";

import { useCallback } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { keepPreviousData } from "@tanstack/react-query";
import { Eye, EyeOff, ListOrdered, SearchX, TriangleAlert } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Missing, PanelError, StaleLine, WaitsLine } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { DeltaBadge } from "@/components/pulso/delta-badge";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

type Page = components["schemas"]["PopularPage"];
type Row = components["schemas"]["PopularRow"];
type Set = (next: Record<string, string | null>) => void;

const IMPORT = "/admin/data-health#import";
const DAY = 86_400_000;
const date = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const weekOf = (iso: string) => `week of ${date.format(new Date(iso))}`;
const before = (iso: string) => new Date(Date.parse(iso) - 7 * DAY).toISOString().slice(0, 10);
const count = (n: number) => n.toLocaleString("en-US");
const leaf = (category: string | null) => (category ? category.replaceAll(" > ", " › ") : "All categories");
const box = "rounded-xl border border-border bg-card shadow-card";
const control =
  "h-(--button-h-md) min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) hover:border-border-strong";
const link = "link-inline rounded-sm whitespace-nowrap underline decoration-border-strong underline-offset-2 hover:decoration-current";
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";
// Rank, change and price are numbers: right-aligned and tabular (vault Design/Tables & Data Density).
const COLUMNS = [
  ["Rank", "num w-14"],
  ["Change", "num w-20"],
  ["Product", "text-left"],
  ["Brand", "text-left"],
  ["Availability", "text-left"],
  ["Price", "num"],
] as const;

// P2-29 b (DEC-272): one Google report (country × category × week) at a time, newest week first. The URL holds the
// week, category and brand choice; replacing it keeps Back for the previous page, like Discover.
export function GooglePopular() {
  const params = useSearchParams();
  const all = params.get("brands") === "all";
  const set = useCallback<Set>((next) => {
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
    "/v1/popular-products",
    { params: { query: { week: params.get("week") ?? undefined, category: params.get("category") ?? undefined, include_major_brands: all || undefined } } },
    {
      enabled: useApiReady(),
      pageParamName: "cursor",
      initialPageParam: null, // null, not undefined (DEC-166)
      getNextPageParam: (page) => page.next_cursor,
      placeholderData: keepPreviousData, // the toolbar keeps focus while a new report loads
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  const { data, error } = query;
  if (!data)
    return query.isError ? (
      <section className={box}>
        <PanelError headingLevel="h2" size="md" title="Couldn't load Google popular products" error={error} retry={() => void query.refetch()} />
      </section>
    ) : (
      <Loading />
    );
  const page = data.pages[0];
  if (page.weeks.length === 0) return <NoImport />;
  const rows = data.pages.flatMap((p) => p.rows);
  const listed = page.total - page.hidden;
  return (
    <div className="flex flex-col gap-4">
      <Toolbar page={page} week={params.get("week")} all={all} set={set} />
      {page.as_of && (
        <p className="text-label text-subtle-foreground" aria-live="polite">
          {count(listed)} {listed === 1 ? "product" : "products"}
          {page.hidden > 0 && `, ${count(page.hidden)} from major brands hidden`} · {page.source_name}, as of the{" "}
          <time dateTime={page.as_of}>{weekOf(page.as_of)}</time>
          {page.captured_at && (
            <>
              {" "}
              · imported <time dateTime={page.captured_at}>{formatUtc(page.captured_at)}</time>
            </>
          )}
        </p>
      )}
      {page.stale && (
        <p className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
          <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
          <span className="font-medium">The newest report is for the {weekOf(page.weeks[0])}, {Math.floor((query.dataUpdatedAt - Date.parse(page.weeks[0])) / DAY)} days ago.</span>{" "}
          Google posts each week within about 2 weeks: download the newest and import it.{" "}
          <Link href={IMPORT} className={link}>
            Open CSV import
          </Link>
        </p>
      )}
      {query.isRefetchError && <StaleLine boxed what="Couldn't refresh the report" error={error} asOf={query.dataUpdatedAt} retry={() => void query.refetch()} />}
      {page.as_of && rows.some((row) => row.change.basis === "no_previous_week") && (
        <WaitsLine lead="Weekly change: no source yet.">
          Import {leaf(page.category)} for the {weekOf(before(page.as_of))} to compare ranks.{" "}
          <Link href={IMPORT} className={link}>
            Open CSV import
          </Link>
        </WaitsLine>
      )}
      {rows.length === 0 ? (
        <NoRows page={page} set={set} />
      ) : (
        <>
          <Table rows={rows} page={page} />
          <LoadMore
            note={`${count(rows.length)} of ${count(listed)} loaded`}
            label="Load more"
            more={query.hasNextPage}
            pending={query.isFetchingNextPage}
            error={query.isFetchNextPageError ? error : null}
            errorTitle="Couldn't load more products"
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

function Toolbar({ page, week, all, set }: { page: Page; week: string | null; all: boolean; set: Set }) {
  const shown = page.as_of ?? week ?? page.weeks[0];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Field label="Week">
        {/* A new week keeps the category in view; the newest week leaves the URL clean. */}
        <select aria-label="Week" className={control} value={shown} onChange={(e) => set({ week: e.target.value === page.weeks[0] ? null : e.target.value, category: page.category })}>
          {page.weeks.map((w, i) => (
            <option key={w} value={w}>
              {date.format(new Date(w))}
              {i === 0 && " (newest)"}
            </option>
          ))}
          {!page.weeks.includes(shown) && <option value={shown}>{date.format(new Date(shown))}</option>}
        </select>
      </Field>
      <Field label="Category">
        <select aria-label="Category" className={cn(control, "max-w-64")} value={page.category ?? ""} onChange={(e) => set({ category: e.target.value || null })}>
          {page.categories.map((c) => (
            <option key={c ?? ""} value={c ?? ""}>
              {leaf(c)}
            </option>
          ))}
          {!page.categories.includes(page.category) && <option value={page.category ?? ""}>{leaf(page.category)}</option>}
        </select>
      </Field>
      <Button aria-pressed={all} onClick={() => set({ brands: all ? null : "all" })} className="aria-pressed:border-border-strong aria-pressed:bg-accent sm:ml-auto">
        {all ? <Eye aria-hidden /> : <EyeOff aria-hidden />}
        Show major brands
        {!all && <span className="font-normal text-muted-foreground tabular-nums">({count(page.hidden)} hidden)</span>}
      </Button>
    </div>
  );
}

function Change({ row }: { row: Row }) {
  const c = row.change;
  if (c.basis === "no_previous_week") return <Missing reason={`No source yet: the ${weekOf(before(row.as_of))} isn't imported`} />;
  if (c.basis === "new")
    return (
      <span title={`Not ranked in the ${weekOf(before(row.as_of))}`} className="rounded-sm border border-border px-1 text-micro font-medium text-foreground">
        New
      </span>
    );
  const from = c.basis === "previous_rank" ? ", from Google's previous rank" : "";
  return (
    <span title={`Rank ${c.previous_rank} in the ${weekOf(before(row.as_of))}${from}`}>
      <DeltaBadge value={c.value} digits={0} />
      <span className="sr-only"> places</span>
    </span>
  );
}

function Price({ row }: { row: Row }) {
  const [low, high] = [row.price_min_minor, row.price_max_minor];
  if (row.currency == null || low == null) return <Missing reason="No price in Google's report" />;
  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: row.currency, trailingZeroDisplay: "stripIfInteger" });
  const unit = 10 ** (money.resolvedOptions().maximumFractionDigits ?? 2);
  return (
    <>
      {money.format(low / unit)}
      {high != null && high !== low && <>–{money.format(high / unit)}</>}
    </>
  );
}

// Dense table: sticky header, tabular numbers. Rows never animate (Motion System rule 2). A row whose GTIN reaches a
// live product links to it; the rest still show (DEC-267 c).
function Table({ rows, page }: { rows: Row[]; page: Page }) {
  const source = `${page.source_name} · ${page.as_of ? weekOf(page.as_of) : ""}${page.captured_at ? ` · imported ${formatUtc(page.captured_at)}` : ""}`;
  return (
    <div role="region" aria-label="Google popular products" tabIndex={0} className={cn(box, "relative max-h-[max(24rem,calc(100dvh-20rem))] overflow-auto overscroll-contain")}>
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
        <tbody>
          {rows.map((row) => (
            <tr key={row.rank} className="row-h hover:bg-(--table-row-hover)">
              <td className={cn(cell, "num text-muted-foreground")} title={source}>
                {count(row.rank)}
              </td>
              <td className={cn(cell, "num")}>
                <Change row={row} />
              </td>
              <th scope="row" className={cn(cell, "max-w-104 text-left font-normal")}>
                {row.product_id ? (
                  <Link href={`/products/${row.product_id}`} title={row.title} className="block truncate rounded-sm font-medium text-foreground hover:underline">
                    {row.title}
                  </Link>
                ) : (
                  <span title={row.title} className="block truncate text-foreground">
                    {row.title}
                  </span>
                )}
              </th>
              <td className={cn(cell, "max-w-48")}>
                <span className="flex min-w-0 items-center gap-1.5">
                  {row.brand ? <span className="truncate" title={row.brand}>{row.brand}</span> : <Missing reason="No brand in Google's report" />}
                  {row.major_brand && <span className="rounded-sm border border-border px-1 text-micro text-muted-foreground">Major</span>}
                </span>
              </td>
              <td className={cn(cell, "text-muted-foreground")}>{row.availability ?? <Missing reason="No availability in Google's report" />}</td>
              <td className={cn(cell, "num")}>
                <Price row={row} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NoRows({ page, set }: { page: Page; set: Set }) {
  return (
    <section className={box}>
      {page.total > 0 ? (
        <EmptyState icon={SearchX} headingLevel="h2" title={`All ${count(page.total)} products are from major brands`} action={<Button onClick={() => set({ brands: "all" })}>Show major brands</Button>}>
          Every brand in this report has {page.major_brand_rows} or more products in it.
        </EmptyState>
      ) : (
        <EmptyState icon={SearchX} headingLevel="h2" title="No report for this week and category" action={<Button onClick={() => set({ week: null, category: null })}>Show the newest week</Button>}>
          Pick another week or category, or import this report in Data Health › CSV import.
        </EmptyState>
      )}
    </section>
  );
}

function NoImport() {
  return (
    <section className={box}>
      <EmptyState
        icon={ListOrdered}
        headingLevel="h2"
        title="No Google popular report yet"
        action={
          <Button asChild variant="secondary">
            <Link href={IMPORT}>Open CSV import</Link>
          </Button>
        }
      >
        In Merchant Center, open Analytics › Products › Popular products, pick a category and a week, and download the CSV. Import it in Data Health as
        “Google Merchant Center Popular products”.
      </EmptyState>
    </section>
  );
}

function Loading() {
  return (
    <div aria-hidden className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-(--button-h-md) w-44" />
        <Skeleton className="h-(--button-h-md) w-60" />
        <Skeleton className="h-(--button-h-md) w-52 sm:ml-auto" />
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
  );
}
