"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as m from "motion/react-m";
import { ArrowRight, Check, CircleSlash, ExternalLink, Info, Timer, TrendingUp, TriangleAlert, Truck, Warehouse } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Ago, PanelError, StaleLine, TapTooltip } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { EmptyState } from "@/components/pulso/empty-state";
import { Metric, type Stat } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { formatAgo, formatDelta, formatUtc } from "@/lib/format";
import { duration } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { type Calc, money, reasons } from "../profit/model";
import { Amount, Computed, MARGIN } from "../profit/profit-tab";
import type { Tab } from "../tabs";
import { count, days, noBestMargin, noFastest, ordersBasis, parseSupplier, shared, short, stars, supplierSearch, type Page, type Row } from "./model";

const tile = "flex min-w-0 flex-col rounded-lg border border-border-subtle bg-background/40";
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";
const link = "link-inline rounded-sm underline decoration-border-strong underline-offset-2 hover:decoration-current";
const tones = { positive: "text-positive", negative: "text-negative", neutral: "text-foreground" };
// Numbers right-aligned (vault Design/Tables & Data Density); the supplier column stays pinned while the rest scroll.
const COLUMNS = [
  ["Supplier", "left"],
  ["Unit cost", "right"],
  ["Ship to US", "right"],
  ["Days", "right"],
  ["Landed cost", "right"],
  ["Margin before ads", "right"],
  ["Rating", "right"],
  ["Orders", "right"],
  ["Years", "right"],
  ["MOQ", "right"],
  ["Warehouse", "left"],
  ["Last seen", "left"],
  ["", "right"],
] as const;
const PLATFORMS: Record<string, string> = { cj: "CJ", aliexpress: "AliExpress", manual: "Manual" };
const platform = (row: Row) => PLATFORMS[row.platform] ?? row.platform;
const LANDED = "Unit cost + freight + duty + customs fee.";

/** An input the calc traced, as a `<Metric>` stat: its observation, or why there is no number. */
function traced(calc: Calc, name: string, value: number | null, reason: string): Stat {
  const trace = calc.sources[name];
  if (value === null || !trace?.as_of) return { reason };
  return { ...trace, as_of: trace.as_of, value, method: null };
}

// UX-6 (vault Features/Product Page - Suppliers, DEC-264): the Best margin and Fastest shipping picks, then every
// matched supplier costed to the US by the Profit tab's own calculation. Opening a supplier in Profit writes
// `supplier=` to the URL, so the choice survives a reload and a shared link. Rows never animate (Motion System rule 2).
export function SuppliersTab({ id, goTo }: { id: string; goTo: (tab: Tab) => void }) {
  const chosen = parseSupplier(useSearchParams());
  const suppliers = $api.useInfiniteQuery(
    "get",
    "/v1/products/{product_id}/suppliers",
    { params: { path: { product_id: id }, query: { country: "US" } } },
    {
      enabled: useApiReady(),
      pageParamName: "cursor",
      initialPageParam: null, // null, not undefined (DEC-166)
      getNextPageParam: (page) => page.next_cursor,
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  const { data, error, hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = suppliers;
  const first: Page | undefined = data?.pages[0];
  const rows: Row[] = data?.pages.flatMap((p) => p.rows) ?? [];
  const now = suppliers.dataUpdatedAt;
  const retry = () => void suppliers.refetch();
  // Native history, like the tab bar; goTo then switches to Profit and focuses its tab.
  const open = (row: Row) => {
    window.history.replaceState(null, "", `?${supplierSearch(window.location.search, row.listing_id)}`);
    goTo("profit");
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="sr-only">Suppliers</h2>
      {data && suppliers.isRefetchError && !isFetchNextPageError && <StaleLine boxed what="Couldn't refresh suppliers" error={error} asOf={now} retry={retry} />}
      {!data && suppliers.isError ? (
        <PanelError headingLevel="h2" size="md" title="Couldn't load suppliers" error={error} retry={retry} />
      ) : first && rows.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="No supplier matched yet"
          action={
            <Button asChild variant="secondary">
              <Link href="/admin/data-health">Import a CSV in Data Health</Link>
            </Button>
          }
        >
          When the matcher links a CJ listing to this product, or you import one, it shows here with its unit cost, US freight
          quote and landed cost.
        </EmptyState>
      ) : (
        <>
          {first ? <Picks page={first} now={now} open={open} /> : <PicksSkeleton />}
          {first && <Gaps rows={rows} goTo={goTo} />}
          {first && <StaleInputs rows={rows} now={now} />}
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <p className="text-label text-subtle-foreground" aria-live="polite">
              {first ? (
                <>
                  {rows.length} {rows.length === 1 ? "supplier" : "suppliers"}
                  {hasNextPage && " loaded"} · best margin first · costed to the US at 1 unit
                  {first.as_of && (
                    <>
                      {" "}
                      · as of <time dateTime={first.as_of}>{formatUtc(first.as_of)}</time>
                    </>
                  )}
                </>
              ) : (
                " "
              )}
            </p>
            <span className="text-micro text-subtle-foreground max-md:hidden" aria-hidden>
              <Kbd>J</Kbd> <Kbd>K</Kbd> move · <Kbd>Enter</Kbd> opens in Profit · <Kbd>O</Kbd> opens the listing
            </span>
          </div>
          <SupplierTable rows={first ? rows : null} chosen={chosen} now={now} open={open} />
          {first && <SupplierCards rows={rows} chosen={chosen} now={now} open={open} />}
          {first && (
            <p className="text-micro text-subtle-foreground">
              Landed cost and margin are the Profit tab&apos;s numbers for each supplier, from your{" "}
              <Link href="/settings" className={link}>
                Settings
              </Link>
              . Days are the carrier&apos;s estimate to the US; supplier processing time comes on top.
            </p>
          )}
          {(hasNextPage || isFetchNextPageError) && (
            <LoadMore
              note={`${rows.length} suppliers shown`}
              label="Load more suppliers"
              more={!!hasNextPage}
              pending={isFetchingNextPage}
              error={isFetchNextPageError ? error : null}
              errorTitle="Couldn't load more suppliers"
              onLoad={() => void fetchNextPage()}
            />
          )}
        </>
      )}
    </div>
  );
}

function Picks({ page, now, open }: { page: Page; now: number; open: (row: Row) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {(["best_margin", "fastest"] as const).map((kind, i) => (
        // The two cards fade in once, staggered; opacity only (vault Features/Product Page - Suppliers, Motion).
        <m.div key={kind} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: duration.base, delay: i * 0.04 }} className="flex">
          <PickCard kind={kind} row={page.picks[kind]} why={kind === "best_margin" ? noBestMargin(page) : noFastest(page)} now={now} open={open} />
        </m.div>
      ))}
    </div>
  );
}

function PickCard({ kind, row, why, now, open }: { kind: "best_margin" | "fastest"; row: Row | null; why: string | null; now: number; open: (row: Row) => void }) {
  const best = kind === "best_margin";
  const Icon = best ? TrendingUp : Timer;
  const title = best ? "Best margin" : "Fastest shipping";
  const calc = row?.cost;
  return (
    <section aria-label={title} className={cn(tile, "w-full gap-1.5 px-4 py-3")}>
      <h3 className="flex items-center gap-1.5 text-label font-medium text-muted-foreground">
        <Icon className="size-3.5 text-brand" aria-hidden />
        {title}
      </h3>
      {row && calc ? (
        <>
          <p className="truncate text-body font-medium text-foreground" title={row.title}>
            {row.supplier_name} <span className="text-label font-normal text-subtle-foreground">· {platform(row)}</span>
          </p>
          <div className="flex flex-wrap items-baseline gap-x-2 font-mono text-stat-lg font-semibold">
            {best && calc.margin_bps !== null && calc.margin_minor !== null ? (
              <>
                <MarginValue calc={calc} now={now} />
                <span className="font-sans text-label font-normal text-muted-foreground">{money(calc.margin_minor)} per order before ads</span>
              </>
            ) : (
              <>
                <span className="text-foreground">{days(calc.freight_min_days, calc.freight_max_days)?.replace(/ d$/, "")}</span>
                <span className="font-sans text-label font-normal text-muted-foreground">days by {calc.method} to the US</span>
              </>
            )}
          </div>
          <p className="text-micro text-subtle-foreground">
            {calc.landed_cost_minor !== null ? `Landed ${money(calc.landed_cost_minor)}` : "Landed cost withheld"}
            {best ? ` · ${days(calc.freight_min_days, calc.freight_max_days) ?? "no delivery days"}` : calc.margin_bps !== null ? ` · margin ${(calc.margin_bps / 100).toFixed(1)}%` : ` · ${short(calc)}`}
          </p>
          <Button variant="secondary" size="sm" className="mt-1 self-start" onClick={() => open(row)} aria-label={`Open ${row.supplier_name} in Profit`}>
            Open in Profit
            <ArrowRight aria-hidden />
          </Button>
        </>
      ) : (
        <p className="text-data text-muted-foreground">{why ?? "No pick yet."}</p>
      )}
    </section>
  );
}

function PicksSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {[0, 1].map((i) => (
        <div key={i} className={cn(tile, "gap-2 px-4 py-3")}>
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-3 w-48" />
        </div>
      ))}
    </div>
  );
}

/** What every row lacks, said once: no market price (the store crawler is off, DEC-261) or no duty rate. */
function Gaps({ rows, goTo }: { rows: Row[]; goTo: (tab: Tab) => void }) {
  const gaps = shared(rows);
  if (!gaps.length) return null;
  return (
    <section aria-label="Margins withheld" className="rounded-lg border border-border bg-secondary/40 px-4 py-2.5 text-data text-foreground">
      <p>
        <Info className="mr-1.5 inline size-3.5 align-[-2px] text-muted-foreground" aria-hidden />
        <span className="font-medium">Margins are withheld for every supplier.</span> Landed costs still compare; Pulso never shows a margin
        from partial costs.
      </p>
      <ul className="mt-1 flex flex-col gap-0.5 pl-5">
        {gaps.includes("price_missing") && (
          <li>
            Pulso has no market price for this product yet.{" "}
            <button type="button" onClick={() => goTo("profit")} className={cn(link, "relative hit-area")}>
              Enter your price on Profit
            </button>
          </li>
        )}
        {gaps.includes("duty_not_set") && (
          <li>
            Settings has no US duty rate, and Pulso never assumes 0%.{" "}
            <Link href="/settings" className={link}>
              Set a US duty rate in Settings
            </Link>
          </li>
        )}
      </ul>
    </section>
  );
}

function StaleInputs({ rows, now }: { rows: Row[]; now: number }) {
  const traces = rows.flatMap((row) => Object.values(row.cost.sources));
  const stale = [...new Map(traces.filter((t) => t.stale && t.as_of).map((t) => [t.source, t])).values()];
  if (!stale.length) return null;
  return (
    <p className="rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
      <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
      <span className="font-medium">Some supplier numbers are older than expected.</span>{" "}
      {stale.map((t) => `${t.source_name} last captured ${formatUtc(t.as_of!)} (${formatAgo(t.as_of!, now)})`).join("; ")}. The
      collector host may be off or the source paused.{" "}
      <Link href="/admin/data-health" className={cn(link, "whitespace-nowrap")}>
        Open Data Health
      </Link>
    </p>
  );
}

/** `quiet` (the supplier list): only a loss is coloured, so the colour marks the rows that need a look. */
function MarginValue({ calc, now, quiet = false }: { calc: Calc; now: number; quiet?: boolean }) {
  const delta = formatDelta(calc.margin_bps! / 100, "up");
  const plain = quiet && delta.tone !== "negative";
  return (
    <Amount
      label="Margin before ads"
      text={`${delta.text}%`}
      hint={<Computed formula={`(${MARGIN}) ÷ sell price.`} calc={calc} now={now} />}
      className={plain ? "text-foreground" : tones[delta.tone]}
    >
      {delta.glyph && !plain && (
        <span aria-hidden className="mr-0.5 text-[0.7em]">
          {delta.glyph}
        </span>
      )}
      {delta.text}%
    </Amount>
  );
}

/** A margin, or why it is withheld: every missing input in words, by hover, focus or tap (R-16). */
function Margin({ calc, now }: { calc: Calc; now: number }) {
  if (calc.complete && calc.margin_bps !== null) return <MarginValue calc={calc} now={now} quiet />;
  return (
    <TapTooltip
      hint={
        <ul className="flex max-w-64 flex-col gap-1 py-0.5">
          {reasons(calc).map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      }
      side="top"
      type="button"
      aria-label={`Margin withheld: ${reasons(calc).join(" ")}`}
      className="relative hit-area inline-flex cursor-help items-center gap-1 rounded-sm text-muted-foreground"
    >
      <span aria-hidden className="text-subtle-foreground">
        —
      </span>
      {short(calc)}
    </TapTooltip>
  );
}

function UnitCost({ row, now }: { row: Row; now: number }) {
  const calc = row.cost;
  const foreign = row.currency !== null && row.currency !== "USD" && row.unit_cost_minor !== null;
  const original = foreign ? money(row.unit_cost_minor!, row.currency!) : null;
  if (foreign && calc.goods_minor === null)
    return (
      <span className="text-muted-foreground" title="No USD rate within 4 days of the supplier price's date. Pulso never guesses a rate.">
        {original} <span className="text-micro text-subtle-foreground">no USD rate</span>
      </span>
    );
  return (
    <span className="whitespace-nowrap">
      <Metric
        stat={traced(calc, "unit_cost", calc.goods_minor, "No supplier price captured yet.")}
        label={original ? `Unit cost, ${original} at the price date's rate` : "Unit cost"}
        format={(v) => money(v)}
        now={now}
      />
      {original && <span className="ml-1 text-micro text-subtle-foreground">{row.currency}</span>}
    </span>
  );
}

function Freight({ row, now }: { row: Row; now: number }) {
  const calc = row.cost;
  if (calc.freight_minor === null) {
    const gap = calc.missing.find((code) => code.startsWith("freight") || code === "fx_missing");
    return (
      <span className="text-muted-foreground" title={reasons({ ...calc, missing: gap ? [gap] : [] }).join(" ")}>
        {calc.missing.includes("freight_missing") || calc.missing.includes("freight_variant_mismatch") ? "Not quoted" : "No USD rate"}
      </span>
    );
  }
  return <Metric stat={traced(calc, "freight", calc.freight_minor, "")} label={`Freight to the US, ${calc.method}`} format={(v) => money(v)} now={now} />;
}

function Landed({ calc, now }: { calc: Calc; now: number }) {
  if (calc.landed_cost_minor === null)
    return (
      <span className="text-subtle-foreground" title={reasons(calc).join(" ")}>
        —
      </span>
    );
  return (
    <Amount label="Landed cost" text={money(calc.landed_cost_minor)} hint={<Computed formula={LANDED} calc={calc} now={now} />} className="font-medium text-foreground">
      {money(calc.landed_cost_minor)}
    </Amount>
  );
}

function Days({ calc }: { calc: Calc }) {
  const text = days(calc.freight_min_days, calc.freight_max_days);
  if (!text) return <span className="text-subtle-foreground">—</span>;
  return <span title={`${calc.method}: the carrier's estimate to the US, before supplier processing`}>{text}</span>;
}

function Terms({ row, now }: { row: Row; now: number }) {
  const tiers = row.bulk_tiers;
  return (
    <span className="inline-flex items-center gap-1.5">
      <Metric stat={row.moq} label="Minimum order quantity" format={String} now={now} />
      {tiers.length > 0 && (
        <TapTooltip
          hint={
            <table className="text-data tabular-nums">
              <caption className="pb-1 text-left font-medium text-foreground">Bulk prices per unit</caption>
              <tbody>
                {tiers.map((t) => (
                  <tr key={t.min_quantity}>
                    <td className="pr-3 text-muted-foreground">{t.min_quantity}+</td>
                    <td className="text-right">{money(t.unit_minor, t.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
          side="top"
          type="button"
          className="relative hit-area cursor-help rounded-sm text-micro text-subtle-foreground underline decoration-dotted underline-offset-4"
        >
          +{tiers.length} {tiers.length === 1 ? "tier" : "tiers"}
        </TapTooltip>
      )}
    </span>
  );
}

function Rating({ row, now }: { row: Row; now: number }) {
  const rating = row.rating;
  return (
    <span className="whitespace-nowrap">
      <Metric stat={rating} label="Rating out of 5" format={stars} now={now} />
      {"count" in rating && rating.count !== null && <span className="ml-1 text-micro text-subtle-foreground">({count(rating.count)})</span>}
    </span>
  );
}

function Orders({ row, now }: { row: Row; now: number }) {
  const orders = row.orders;
  return (
    <span className="whitespace-nowrap">
      <Metric stat={orders} label={"semantics" in orders ? `Orders, ${ordersBasis(orders)}` : "Orders"} format={count} now={now} />
      {"semantics" in orders && <span className="ml-1 text-micro text-subtle-foreground">{ordersBasis(orders)}</span>}
    </span>
  );
}

function WarehouseCell({ row }: { row: Row }) {
  if (!row.warehouse_country) return <span className="text-subtle-foreground" title="The offer states no warehouse">—</span>;
  return row.warehouse_country === "US" ? (
    <span className="inline-flex items-center gap-1 text-foreground">
      <Warehouse className="size-3.5 text-brand" aria-hidden />
      US warehouse
    </span>
  ) : (
    <span className="text-muted-foreground">{row.warehouse_country}</span>
  );
}

function LastSeen({ row, now }: { row: Row; now: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-subtle-foreground">
      {row.stale ? <TriangleAlert aria-hidden className="size-3 shrink-0 text-warning" /> : <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-border-strong" />}
      <Ago iso={row.last_seen} now={now} source={row.source_name} />
      {row.stale && <span className="sr-only">· stale</span>}
    </span>
  );
}

function Badges({ row, chosen }: { row: Row; chosen: number | null }) {
  const badge = "inline-flex h-5 shrink-0 items-center gap-1 rounded-sm px-1.5 text-micro font-medium whitespace-nowrap";
  return (
    <>
      {row.picks.includes("best_margin") && (
        <span className={cn(badge, "bg-brand-muted text-foreground")}>
          <TrendingUp className="size-3 text-brand" aria-hidden />
          Best margin
        </span>
      )}
      {row.picks.includes("fastest") && (
        <span className={cn(badge, "bg-brand-muted text-foreground")}>
          <Timer className="size-3 text-brand" aria-hidden />
          Fastest
        </span>
      )}
      {row.listing_id === chosen && (
        <span className={cn(badge, "border border-brand/50 text-foreground")}>
          <Check className="size-3 text-brand" aria-hidden />
          In Profit
        </span>
      )}
      {!row.in_stock && (
        <span className={cn(badge, "bg-negative-muted text-negative")}>
          <CircleSlash className="size-3" aria-hidden />
          Out of stock
        </span>
      )}
    </>
  );
}

function Name({ row, chosen }: { row: Row; chosen: number | null }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="truncate font-medium text-foreground" title={`${row.title}${row.supplier_country ? ` · supplier in ${row.supplier_country}` : ""}`}>
        {row.supplier_name}
      </span>
      <span className="shrink-0 text-micro text-subtle-foreground">{platform(row)}</span>
      <Badges row={row} chosen={chosen} />
    </span>
  );
}

function Actions({ row, open }: { row: Row; open: (row: Row) => void }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Button asChild variant="ghost" size="icon-sm" className="relative hit-area">
        <a href={row.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${row.supplier_name}'s listing on ${platform(row)}`} title={`Open the listing on ${platform(row)}`}>
          <ExternalLink aria-hidden />
        </a>
      </Button>
      <Button variant="ghost" size="sm" className="relative hit-area" onClick={() => open(row)} aria-label={`Open ${row.supplier_name} in Profit`}>
        Profit
        <ArrowRight aria-hidden />
      </Button>
    </span>
  );
}

/** j/k or arrows move between rows, Enter opens the supplier in Profit, o opens its listing (vault Product Page -
 *  Suppliers, Keyboard). Inner controls keep their own keys. */
function onRowKey(e: React.KeyboardEvent<HTMLElement>, row: Row, open: (row: Row) => void) {
  if (e.target !== e.currentTarget) return;
  const go = (el: Element | null) => el instanceof HTMLElement && (e.preventDefault(), el.focus());
  if (e.key === "j" || e.key === "ArrowDown") go(e.currentTarget.nextElementSibling);
  else if (e.key === "k" || e.key === "ArrowUp") go(e.currentTarget.previousElementSibling);
  else if (e.key === "Enter") {
    e.preventDefault();
    open(row);
  } else if (e.key.toLowerCase() === "o") {
    e.preventDefault();
    window.open(row.url, "_blank", "noopener,noreferrer");
  }
}

/** A click on the row's own surface opens it in Profit; a number, link or button inside keeps its own action. */
const onRowClick = (e: React.MouseEvent<HTMLElement>, row: Row, open: (row: Row) => void) => {
  if (!(e.target as HTMLElement).closest("a, button")) open(row);
};

function SupplierTable({ rows, chosen, now, open }: { rows: Row[] | null; chosen: number | null; now: number; open: (row: Row) => void }) {
  return (
    <div role="region" aria-label="Suppliers" tabIndex={0} className="relative max-h-[max(24rem,calc(100dvh-20rem))] overflow-auto overscroll-contain rounded-lg border border-border max-md:hidden">
      <table className="w-full border-separate border-spacing-0 zone-data">
        <thead className="sticky top-0 z-20 bg-card">
          <tr className="row-h text-label text-muted-foreground">
            {COLUMNS.map(([name, align], i) => (
              <th
                key={name || "actions"}
                scope="col"
                className={cn(cell, "border-border bg-card font-medium", align === "right" ? "text-right" : "text-left", i === 0 && "sticky left-0 z-10")}
              >
                {name || <span className="sr-only">Actions</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows
            ? rows.map((row, i) => {
                const selected = row.listing_id === chosen;
                return (
                  <tr
                    key={row.listing_id}
                    tabIndex={i === 0 ? 0 : -1}
                    aria-label={`${row.supplier_name}, ${row.cost.landed_cost_minor === null ? "landed cost withheld" : `landed ${money(row.cost.landed_cost_minor)}`}`}
                    aria-selected={selected}
                    onKeyDown={(e) => onRowKey(e, row, open)}
                    onClick={(e) => onRowClick(e, row, open)}
                    className={cn("group row-h cursor-pointer outline-ring -outline-offset-2 hover:bg-(--table-row-hover) focus-visible:outline-2", !row.in_stock && "text-muted-foreground")}
                  >
                    {/* The selected supplier keeps a static brand edge (Motion System: no row animation). */}
                    <th
                      scope="row"
                      className={cn(cell, "sticky left-0 z-10 max-w-80 bg-card text-left font-normal group-hover:bg-(--table-row-hover)", selected && "shadow-[inset_2px_0_0_var(--brand)]")}
                    >
                      <Name row={row} chosen={chosen} />
                    </th>
                    <td className={cn(cell, "num")}>
                      <UnitCost row={row} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Freight row={row} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Days calc={row.cost} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Landed calc={row.cost} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Margin calc={row.cost} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Rating row={row} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Orders row={row} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Metric stat={row.years_active} label="Years active" format={(n) => `${n} y`} now={now} />
                    </td>
                    <td className={cn(cell, "num")}>
                      <Terms row={row} now={now} />
                    </td>
                    <td className={cell}>
                      <WarehouseCell row={row} />
                    </td>
                    <td className={cell}>
                      <LastSeen row={row} now={now} />
                    </td>
                    <td className={cn(cell, "px-1.5 text-right")}>
                      <Actions row={row} open={open} />
                    </td>
                  </tr>
                );
              })
            : Array.from({ length: 3 }, (_, i) => (
                <tr key={i} aria-hidden className="row-h">
                  {COLUMNS.map(([name, align], c) => (
                    <td key={name || "actions"} className={cell}>
                      <Skeleton className={cn("h-3.5", c === 0 ? "w-40" : "w-14", align === "right" && "ml-auto")} />
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}

function SupplierCard({ row, chosen, now, open }: { row: Row; chosen: number | null; now: number; open: (row: Row) => void }) {
  const calc = row.cost;
  const fact = "flex flex-col gap-0.5";
  return (
    <li className={cn("flex flex-col gap-2.5 rounded-lg border p-3 zone-data", row.listing_id === chosen ? "border-brand/60" : "border-border-subtle")}>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <Name row={row} chosen={chosen} />
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
        <div className={fact}>
          <dt className="text-label text-muted-foreground">Landed cost</dt>
          <dd className="font-mono text-stat-lg font-semibold">
            <Landed calc={calc} now={now} />
          </dd>
        </div>
        <div className={fact}>
          <dt className="text-label text-muted-foreground">Margin before ads</dt>
          <dd className={cn(calc.complete && "font-mono text-stat-lg font-semibold")}>
            <Margin calc={calc} now={now} />
          </dd>
        </div>
        <div className={fact}>
          <dt className="text-label text-muted-foreground">Unit cost</dt>
          <dd>
            <UnitCost row={row} now={now} />
          </dd>
        </div>
        <div className={fact}>
          <dt className="text-label text-muted-foreground">Ship to US</dt>
          <dd className="flex flex-wrap gap-x-1.5">
            <Freight row={row} now={now} />
            <span className="text-subtle-foreground">
              <Days calc={calc} />
            </span>
          </dd>
        </div>
        <div className={fact}>
          <dt className="text-label text-muted-foreground">Warehouse</dt>
          <dd>
            <WarehouseCell row={row} />
          </dd>
        </div>
        <div className={fact}>
          <dt className="text-label text-muted-foreground">Last seen</dt>
          <dd>
            <LastSeen row={row} now={now} />
          </dd>
        </div>
      </dl>
      <div className="flex items-center gap-2">
        <Button variant="secondary" className="relative hit-area flex-1" onClick={() => open(row)} aria-label={`Open ${row.supplier_name} in Profit`}>
          Open in Profit
          <ArrowRight aria-hidden />
        </Button>
        <Button asChild variant="ghost" size="icon" className="relative hit-area">
          <a href={row.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${row.supplier_name}'s listing on ${platform(row)}`}>
            <ExternalLink aria-hidden />
          </a>
        </Button>
      </div>
    </li>
  );
}

/** Below 768 px each supplier is a card with Open in Profit full width (UX spec, Responsive). */
function SupplierCards({ rows, chosen, now, open }: { rows: Row[]; chosen: number | null; now: number; open: (row: Row) => void }) {
  return (
    <ul aria-label="Suppliers" className="flex flex-col gap-2 md:hidden">
      {rows.map((row) => (
        <SupplierCard key={row.listing_id} row={row} chosen={chosen} now={now} open={open} />
      ))}
    </ul>
  );
}
