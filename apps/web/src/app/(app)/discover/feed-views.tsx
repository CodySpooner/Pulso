"use client";

import { useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Package } from "lucide-react";

import { DeltaBadge } from "@/components/pulso/delta-badge";
import { Metric, type Stat } from "@/components/pulso/metric";
import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/schema";
import { formatAgo, formatDelta, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

// openapi-fetch drops a key typed only `null` from responses, so each NoSource arrives as `{reason}` (DEC-238 g).
type Loose<T> = T extends { reason: string } ? { reason: string; value?: null } : T;
export type Item = { [K in keyof components["schemas"]["DiscoverItem"]]: Loose<components["schemas"]["DiscoverItem"][K]> };
/** Sources feeding the feed that are blocked or disabled: a card they feed gets a red freshness dot. */
export type Paused = Set<string>;

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", trailingZeroDisplay: "stripIfInteger" });
const money = (minor: number) => usd.format(minor / 100);
const count = (n: number) => n.toLocaleString("en-US");
const perWeek = (n: number) => `${count(n)}/7d`;
const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const leaf = (path: string | null) => path?.split(" > ").at(-1) ?? "Uncategorised";
const sourced = (stats: Stat[]) => stats.filter((s): s is Exclude<Stat, { reason: string }> => !("reason" in s));

function Price({ item, now }: { item: Item; now: number }) {
  if ("reason" in item.price_min_minor) return <Metric stat={item.price_min_minor} label="Retail price" format={money} now={now} />;
  return (
    <span className="whitespace-nowrap">
      <Metric stat={item.price_min_minor} label="Lowest retail price" format={money} now={now} />
      <span aria-hidden className="mx-0.5 text-subtle-foreground">–</span>
      <Metric stat={item.price_max_minor} label="Highest retail price" format={money} now={now} />
    </span>
  );
}

function Velocity({ item, now }: { item: Item; now: number }) {
  const v = item.velocity;
  if ("reason" in v) return <Metric stat={v} label="Velocity" missing="Insufficient signal" format={perWeek} now={now} />;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <Metric stat={v} label={`Velocity, ${v.family} grade ${v.grade}`} format={perWeek} now={now} />
      <span className="rounded-sm border border-border px-1 text-micro text-muted-foreground" title={`Grade ${v.grade}`}>
        <span className="sr-only">Grade </span>
        {v.grade === "unproven" ? "?" : v.grade}
      </span>
      {v.gap && (
        <span className="rounded-sm border border-warning/40 bg-warning-muted px-1 text-micro text-foreground" title="The 7-day window overlaps a collection gap">
          gap
        </span>
      )}
    </span>
  );
}

/** G7, the momentum sort key, signed with ▲/▼ (never colour alone). */
function Momentum({ item, now }: { item: Item; now: number }) {
  const v = item.velocity;
  if ("reason" in v) return <DeltaBadge value={null} missingReason="Insufficient signal: no momentum" />;
  const delta = formatDelta(v.growth, "up", 2);
  const tone = { positive: "text-positive", negative: "text-negative", neutral: "text-muted-foreground" }[delta.tone];
  return <Metric stat={{ ...v, value: v.growth }} label="Momentum, 7-day log growth" format={() => `${delta.glyph ?? ""} ${delta.text}`.trim()} now={now} className={tone} />;
}

/** The oldest family feeding the item: amber when stale, red when a feeding source is paused, said in words too. */
function Freshness({ item, now, paused }: { item: Item; now: number; paused: Paused }) {
  const stats = sourced([item.store_count, item.supplier_count, item.velocity]);
  const off = stats.some((s) => paused.has(s.source));
  const state = off ? "source paused" : item.stale ? "stale" : null;
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", off ? "text-negative" : item.stale ? "text-warning" : "text-subtle-foreground")}>
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", off ? "bg-negative" : item.stale ? "bg-warning" : "bg-border-strong")} />
      {item.as_of ? (
        <time dateTime={item.as_of} title={`Oldest data on this product: ${formatUtc(item.as_of)}`}>
          {formatAgo(item.as_of, now)}
        </time>
      ) : (
        "Not collected yet"
      )}
      {state && <span>· {state}</span>}
    </span>
  );
}

function Thumb({ url, className }: { url: string | null; className: string }) {
  const [broken, setBroken] = useState(false);
  if (!url || broken)
    return (
      <div className={cn("grid place-items-center bg-secondary text-subtle-foreground", className)}>
        <Package className="size-1/3 max-h-8 max-w-8" strokeWidth={1.5} aria-hidden />
      </div>
    );
  // eslint-disable-next-line @next/next/no-img-element -- listing images come from any store or supplier CDN; next/image would need each host allow-listed
  return <img src={url} alt="" loading="lazy" decoding="async" onError={() => setBroken(true)} className={cn("bg-secondary object-cover", className)} />;
}

const href = (item: Item) => `/products/${item.id}`;

// Image-first card (vault Features/Discover, card anatomy). The title link stretches over the card, so a click or
// Enter anywhere opens the product; each number sits above it and opens its own provenance card. Cards never
// animate in, so cards loaded by infinite scroll don't either (Motion System rule 2).
export function ProductCard({ item, now, paused }: { item: Item; now: number; paused: Paused }) {
  return (
    <article className="group relative flex min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card transition-[border-color,scale] duration-(--duration-fast) ease-standard hover:border-border-strong has-[a:active]:scale-[0.99] has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-2 has-[a:focus-visible]:outline-ring">
      <div className="aspect-square overflow-hidden border-b border-border-subtle">
        <Thumb url={item.image_url} className="size-full transition-transform duration-(--duration-slow) ease-out group-hover:scale-[1.03]" />
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3 zone-data">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="line-clamp-2 font-medium text-foreground" title={item.title}>
            <Link href={href(item)} className="outline-none after:absolute after:inset-0">
              {item.title}
            </Link>
          </h2>
          <p className="truncate text-label text-subtle-foreground" title={item.category ?? undefined}>
            {leaf(item.category)} · <time dateTime={item.first_seen_at}>{day.format(new Date(item.first_seen_at))}</time>
          </p>
        </div>
        <dl className="relative z-10 grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1 pointer-coarse:gap-y-6 [&_dd]:justify-self-end [&_dd]:text-right [&_dt]:text-muted-foreground">
          <dt className="max-md:hidden">Price</dt>
          <dd className="max-md:hidden">
            <Price item={item} now={now} />
          </dd>
          <dt>Velocity</dt>
          <dd>
            <Velocity item={item} now={now} />
          </dd>
          <dt>Momentum</dt>
          <dd>
            <Momentum item={item} now={now} />
          </dd>
          <dt className="max-md:hidden">Stores</dt>
          <dd className="max-md:hidden">
            <Metric stat={item.store_count} label="Stores selling it" format={count} now={now} /> ·{" "}
            <Metric stat={item.supplier_count} label="Matched suppliers" format={(n) => `${count(n)} sup.`} now={now} />
          </dd>
          <dt>Margin</dt>
          <dd>
            <Metric stat={item.best_margin_minor} label="Best landed margin" format={money} now={now} />
          </dd>
        </dl>
        <p className="mt-auto pt-1 text-micro">
          <Freshness item={item} now={now} paused={paused} />
        </p>
      </div>
    </article>
  );
}

export const GRID = "grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4 xl:grid-cols-5 min-[1600px]:grid-cols-6";

export function CardSkeletons({ n }: { n: number }) {
  return Array.from({ length: n }, (_, i) => (
    <div key={i} aria-hidden className="flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-card">
      <Skeleton className="aspect-square rounded-none" />
      <div className="flex flex-col gap-2 p-3">
        <Skeleton className="h-4 w-4/5" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="mt-1 h-3.5 w-full" />
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-2/3" />
      </div>
    </div>
  ));
}

const COLUMNS = ["Product", "Price", "Velocity", "Momentum", "Stores", "Suppliers", "Best margin", "First seen", "Freshness"];
const OVERSCAN = 10;
const cell = "border-b border-border-subtle px-3 whitespace-nowrap";

/** Rows [start, end) of a fixed-height table that the scroller shows, plus overscan, and the row height. */
function useRowWindow(scroller: React.RefObject<HTMLDivElement | null>, rows: number) {
  const [range, setRange] = useState({ start: 0, end: Math.min(rows, 40), rowH: 32 });
  useLayoutEffect(() => {
    const el = scroller.current!;
    const update = () => {
      // ponytail: the density token is in rem and fixed per pointer type, so rows are never measured.
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      const rowH = parseFloat(getComputedStyle(el).getPropertyValue("--table-row-h")) * rem;
      const start = Math.max(0, Math.floor(el.scrollTop / rowH) - OVERSCAN);
      const end = Math.min(rows, Math.ceil((el.scrollTop + el.clientHeight) / rowH) + OVERSCAN);
      setRange((r) => (r.start === start && r.end === end && r.rowH === rowH ? r : { start, end, rowH }));
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const resize = new ResizeObserver(update);
    resize.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      resize.disconnect();
    };
  }, [scroller, rows]);
  return range;
}

// Dense table (vault Design/Tables & Data Density): sticky header, pinned product column, tabular right-aligned
// numbers. Only the rows in view render (fixed row height, overscan 10); rows never animate (Motion System rule 2).
// The name is a real link; a click anywhere else on the row opens it too.
export function ProductTable({
  items,
  now,
  paused,
  loadingMore,
  onNearEnd,
}: {
  items: Item[];
  now: number;
  paused: Paused;
  loadingMore: boolean;
  onNearEnd: () => void;
}) {
  const router = useRouter();
  const scroller = useRef<HTMLDivElement>(null);
  const { start, end, rowH } = useRowWindow(scroller, items.length);
  const near = end >= items.length - OVERSCAN;
  useLayoutEffect(() => {
    if (near) onNearEnd();
  }, [near, items.length, onNearEnd]);
  return (
    <div
      ref={scroller}
      role="region"
      aria-label="Products"
      tabIndex={0}
      className="relative max-h-[max(24rem,calc(100dvh-17rem))] overflow-auto overscroll-contain rounded-xl border border-border bg-card shadow-card"
    >
      <table aria-rowcount={items.length + 1} className="w-full min-w-240 border-separate border-spacing-0 zone-data">
        <thead className="sticky top-0 z-20 bg-card">
          <tr className="row-h text-label text-muted-foreground" aria-rowindex={1}>
            {COLUMNS.map((name, i) => (
              <th key={name} scope="col" className={cn(cell, "border-border bg-card font-medium", i === 0 ? "sticky left-0 z-10 text-left" : "text-right")}>
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {start > 0 && <tr aria-hidden style={{ height: start * rowH }} />}
          {items.slice(start, end).map((item, i) => (
            <tr
              key={item.id}
              aria-rowindex={start + i + 2}
              className="group row-h cursor-pointer hover:bg-(--table-row-hover)"
              onClick={(e) => {
                if (!(e.target as HTMLElement).closest("a, button")) router.push(href(item));
              }}
            >
              <th scope="row" className={cn(cell, "sticky left-0 z-10 max-w-80 bg-card text-left font-normal group-hover:bg-(--table-row-hover)")}>
                <span className="flex items-center gap-2 max-md:w-40">
                  <Thumb url={item.image_url} className="size-6 shrink-0 rounded-sm" />
                  <span className="flex min-w-0 items-baseline gap-2">
                    <Link href={href(item)} title={item.title} className="truncate rounded-sm font-medium text-foreground hover:underline">
                      {item.title}
                    </Link>
                    <span className="truncate text-label text-subtle-foreground max-md:hidden" title={item.category ?? undefined}>
                      {leaf(item.category)}
                    </span>
                  </span>
                </span>
              </th>
              <td className={cn(cell, "num")}>
                <Price item={item} now={now} />
              </td>
              <td className={cn(cell, "num")}>
                <Velocity item={item} now={now} />
              </td>
              <td className={cn(cell, "num")}>
                <Momentum item={item} now={now} />
              </td>
              <td className={cn(cell, "num")}>
                <Metric stat={item.store_count} label="Stores selling it" format={count} now={now} />
              </td>
              <td className={cn(cell, "num")}>
                <Metric stat={item.supplier_count} label="Matched suppliers" format={count} now={now} />
              </td>
              <td className={cn(cell, "num")}>
                <Metric stat={item.best_margin_minor} label="Best landed margin" format={money} now={now} />
              </td>
              <td className={cn(cell, "num text-muted-foreground")}>
                <time dateTime={item.first_seen_at} title={formatUtc(item.first_seen_at)}>
                  {day.format(new Date(item.first_seen_at))}
                </time>
              </td>
              <td className={cn(cell, "text-right text-label")}>
                <Freshness item={item} now={now} paused={paused} />
              </td>
            </tr>
          ))}
          {end < items.length && <tr aria-hidden style={{ height: (items.length - end) * rowH }} />}
          {loadingMore && <SkeletonRows n={3} />}
        </tbody>
      </table>
    </div>
  );
}

export function SkeletonRows({ n }: { n: number }) {
  return Array.from({ length: n }, (_, i) => (
    <tr key={i} aria-hidden className="row-h">
      {COLUMNS.map((name, c) => (
        <td key={name} className={cn(cell, c === 0 && "sticky left-0 bg-card")}>
          <Skeleton className={cn("h-3.5", c === 0 ? "w-48" : "ml-auto w-14")} />
        </td>
      ))}
    </tr>
  ));
}

export function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
      <table className="w-full min-w-240 border-separate border-spacing-0 zone-data" aria-hidden>
        <thead>
          <tr className="row-h text-label text-muted-foreground">
            {COLUMNS.map((name, i) => (
              <th key={name} className={cn(cell, "border-border font-medium", i === 0 ? "text-left" : "text-right")}>
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <SkeletonRows n={12} />
        </tbody>
      </table>
    </div>
  );
}
