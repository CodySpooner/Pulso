"use client";

import { Box, ChevronRight, Megaphone, Store } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { Panel, PanelError, StaleLine } from "@/components/data-health/atoms";
import { Metric, type Stat } from "@/components/pulso/metric";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatDelta, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { card, newest, StatCard } from "./stat-card";
import { TABS, type Tab } from "./tabs";

type Velocity = components["schemas"]["Velocity"];

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const money = (minor: number) => usd.format(minor / 100);
const count = (n: number) => n.toLocaleString("en-US");
const perWeek = (n: number) => `${count(n)}/7d`;
const ago = (days: number) => (days === 0 ? "Today" : days === 1 ? "1 day ago" : `${count(days)} days ago`);
const day = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });
const platform = (key: string) => (key.length <= 3 ? key.toUpperCase() : key[0].toUpperCase() + key.slice(1));
const chip = "rounded-sm border px-1 font-sans text-micro font-normal";
// Card spans keep both grids full: phone 2 + 2 + 2 (price on its own row), desktop 3 + 2 (velocity wide).
const SKELETON_SPANS = ["col-span-2 md:col-span-1", "", "", "", "md:col-span-2 3xl:col-span-1"];

// UX-4 (vault Features/Product Page - Overview): the Phase 2 key stats and where the product appears. Trend Score,
// Saturation and Lifecycle arrive with Phase 4 scores behind ff_scores; until then the grid holds the five cards
// below, not empty score cards. States: skeleton, panel error, stale line, per-card stale and no source yet.
export function Overview({ id, goTo }: { id: string; goTo: (tab: Tab) => void }) {
  const overview = $api.useQuery(
    "get",
    "/v1/products/{product_id}/overview",
    { params: { path: { product_id: id } } },
    // A 4xx won't change on a retry (a merge while the page was open is a 409).
    { enabled: useApiReady(), retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1 },
  );
  const { data, error } = overview;
  const retry = () => void overview.refetch();
  if (!data)
    return overview.isError ? (
      <section className={card}>
        <PanelError headingLevel="h2" title="Couldn't load the overview" error={error} retry={retry} />
      </section>
    ) : (
      <OverviewSkeleton />
    );

  const now = overview.dataUpdatedAt;
  const prices = [data.price_min_minor, data.price_max_minor];
  const cost = data.best_supplier_cost_minor;
  const velocity = data.velocity;
  return (
    <div className="flex flex-col gap-4">
      {overview.isError && <StaleLine boxed what="Couldn't refresh the overview" error={error} asOf={now} retry={retry} />}
      <section aria-labelledby="key-stats">
        <h2 id="key-stats" className="sr-only">
          Key stats
        </h2>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 3xl:grid-cols-5">
          <StatCard
            label="Price range"
            stat={newest(prices) ?? data.price_min_minor}
            now={now}
            className="col-span-2 md:col-span-1"
            detail={
              !("reason" in data.price_median_minor) && (
                <>
                  Median <Metric stat={data.price_median_minor} label="Median retail price" format={money} now={now} className="font-mono text-foreground" />
                </>
              )
            }
          >
            {"reason" in data.price_min_minor ? (
              <Metric stat={data.price_min_minor} label="Retail price" format={money} now={now} />
            ) : (
              <span className="whitespace-nowrap">
                <Metric stat={data.price_min_minor} label="Lowest retail price" format={money} now={now} />
                <span aria-hidden className="mx-1.5 text-subtle-foreground">–</span>
                <Metric stat={data.price_max_minor} label="Highest retail price" format={money} now={now} />
              </span>
            )}
          </StatCard>
          <StatCard label="Best supplier cost" stat={cost} now={now} detail={!("reason" in cost) && `Lowest in-stock unit cost · ${platform(cost.platform)}`}>
            <Metric stat={cost} label="Best supplier cost" format={money} now={now} />
          </StatCard>
          <StatCard label="Landed margin" stat={data.landed_margin_minor} now={now}>
            <Metric stat={data.landed_margin_minor} label="Landed margin" format={money} now={now} />
          </StatCard>
          <StatCard label="First seen" stat={data.age_days} now={now} detail={<Metric stat={data.age_days} label="Days since first seen" format={ago} now={now} />}>
            <time dateTime={data.first_seen_at} title={formatUtc(data.first_seen_at)} className="whitespace-nowrap">
              {day.format(new Date(data.first_seen_at))}
            </time>
          </StatCard>
          <StatCard
            label="Velocity 7d"
            stat={velocity}
            now={now}
            className="md:col-span-2 3xl:col-span-1"
            detail={!("reason" in velocity) && <Momentum v={velocity} now={now} />}
          >
            {"reason" in velocity ? (
              <Metric stat={velocity} label="Velocity 7d" missing="Insufficient signal" format={perWeek} now={now} />
            ) : (
              <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
                <Metric stat={velocity} label={`Velocity 7d, ${velocity.method}`} format={perWeek} now={now} />
                <span className={cn(chip, "border-border text-muted-foreground")}>Grade {velocity.grade === "unproven" ? "?" : velocity.grade}</span>
                {velocity.grade === "B" && <span className={cn(chip, "border-border text-muted-foreground")}>lower bound</span>}
                {velocity.gap && (
                  <span className={cn(chip, "border-warning/40 bg-warning-muted text-foreground")} title="The 7-day window overlaps a collection gap">
                    gap
                  </span>
                )}
              </span>
            )}
          </StatCard>
        </dl>
      </section>
      <Appears data={data} now={now} goTo={goTo} />
    </div>
  );
}

/** G7, the momentum Discover sorts by, signed with ▲/▼ (never colour alone). */
function Momentum({ v, now }: { v: Velocity; now: number }) {
  const delta = formatDelta(v.growth, "up", 2);
  const tone = { positive: "text-positive", negative: "text-negative", neutral: "text-muted-foreground" }[delta.tone];
  return (
    <span className="whitespace-nowrap">
      <Metric
        stat={{ ...v, value: v.growth }}
        label="Momentum, 7-day log growth"
        format={() => `${delta.glyph ?? ""} ${delta.text}`.trim()}
        now={now}
        className={cn("font-mono", tone)}
      />{" "}
      momentum
    </span>
  );
}

const KINDS = {
  supplier: { label: "Suppliers", icon: Box, tab: "suppliers", none: "No supplier listing matched yet." },
  store: { label: "Stores", icon: Store, tab: "sellers", none: "No store listing matched yet." },
} as const;
const row = "grid min-h-11 grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-x-3 border-b border-border-subtle px-4 py-1.5 last:border-b-0";

/** Counts per source, each opening its tab; a kind with no listing, and ads, read "No source yet", never 0. */
function Appears({ data, now, goTo }: { data: { appearances: { vendor: "store" | "supplier"; count: Stat }[]; ad_count: Stat }; now: number; goTo: (tab: Tab) => void }) {
  const rows = (["supplier", "store"] as const).flatMap((vendor) => {
    const found = data.appearances.filter((a) => a.vendor === vendor).map((a) => ({ vendor, stat: a.count }));
    return found.length > 0 ? found : [{ vendor, stat: { reason: KINDS[vendor].none } as Stat }];
  });
  return (
    <Panel id="appears" title="Where it appears">
      <ul>
        {rows.map(({ vendor, stat }, i) => {
          const kind = KINDS[vendor];
          const tab = TABS.find((t) => t.value === kind.tab)!.label;
          const where = "reason" in stat ? kind.label : `${kind.label} on ${stat.source_name}`;
          return (
            <li key={i} className={row}>
              <kind.icon className="size-4 text-muted-foreground" aria-hidden />
              <span className="min-w-0 truncate text-body text-foreground">
                {kind.label}
                <span className="ml-2 text-label text-subtle-foreground">{"reason" in stat ? stat.reason : stat.source_name}</span>
              </span>
              <Metric stat={stat} label={where} format={count} now={now} className={cn("justify-self-end text-body", !("reason" in stat) && "font-mono text-foreground")} />
              <Button variant="ghost" size="sm" onClick={() => goTo(kind.tab)} aria-label={`Open the ${tab} tab`} className="-mr-2">
                {tab}
                <ChevronRight aria-hidden />
              </Button>
            </li>
          );
        })}
        <li className={row}>
          <Megaphone className="size-4 text-muted-foreground" aria-hidden />
          <span className="min-w-0 truncate text-body text-foreground">
            Ads
            {"reason" in data.ad_count && <span className="ml-2 text-label text-subtle-foreground">{data.ad_count.reason}</span>}
          </span>
          <Metric stat={data.ad_count} label="Ads" format={count} now={now} className="justify-self-end text-body" />
          <span />
        </li>
      </ul>
    </Panel>
  );
}

function OverviewSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 3xl:grid-cols-5">
        {SKELETON_SPANS.map((span, i) => (
          <div key={i} className={cn("flex flex-col gap-1 px-4 py-3", card, span)}>
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-7 w-28" />
            <Skeleton className="h-4.5 w-24" />
            <Skeleton className="h-3.5 w-32" />
          </div>
        ))}
      </div>
      <div className={card}>
        <div className="flex min-h-12 items-center border-b border-border-subtle px-4">
          <Skeleton className="h-5 w-36" />
        </div>
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex min-h-11 items-center gap-3 border-b border-border-subtle px-4 last:border-b-0">
            <Skeleton className="size-4" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="ml-auto h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}
