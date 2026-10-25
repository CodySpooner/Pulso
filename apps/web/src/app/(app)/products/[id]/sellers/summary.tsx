"use client";

import * as m from "motion/react-m";
import { Calculator } from "lucide-react";

import { Ago } from "@/components/data-health/atoms";
import { Skeleton } from "@/components/ui/skeleton";
import { duration } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { money, sparkSegments, stripScale, type Page } from "./model";

const tile = "flex min-w-0 flex-col gap-2 rounded-lg border border-border-subtle bg-background/40 p-3";
const SOURCE = "Shopify stores";

// The summary strip (vault Features/Product Page - Sellers, UX spec): spread, sellers over 90 days, suggested band.
export function Summary({ page, now }: { page: Page; now: number }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <SpreadTile page={page} now={now} />
      <SellersTile page={page} now={now} />
      <BandTile />
    </div>
  );
}

function Footer({ asOf, now, children }: { asOf: string | null; now: number; children?: React.ReactNode }) {
  return (
    <p className="mt-auto text-micro text-subtle-foreground">
      {children}
      {children && " · "}
      {asOf ? (
        <>
          {SOURCE} · <Ago iso={asOf} now={now} source={SOURCE} />
        </>
      ) : (
        "No snapshot yet"
      )}
    </p>
  );
}

/** One dot per active seller between the lowest and highest price, the middle 50% shaded, the median ticked. */
function SpreadTile({ page, now }: { page: Page; now: number }) {
  const s = page.spread;
  const x = stripScale(s.min, s.max);
  const at = (price: number) => `${(4 + x!(price) * 92).toFixed(2)}%`; // 4% inset, so edge dots stay whole
  const left = [s.missing > 0 && `${s.missing} without a USD price`, s.untrackable > 0 && `${s.untrackable} untrackable`].filter(Boolean);
  return (
    <section aria-labelledby="spread-title" className={tile}>
      <h3 id="spread-title" className="text-label text-muted-foreground">
        Price spread
      </h3>
      {x && s.min !== null && s.max !== null ? (
        <>
          <p className="font-mono text-stat-lg font-semibold text-foreground tabular-nums">
            {s.n === 1 ? money(s.min) : `${money(s.min)}–${money(s.max)}`}
          </p>
          <p className="text-label text-muted-foreground tabular-nums">
            median {money(s.median!)} · mean {money(s.mean!)}
          </p>
          <svg role="img" aria-label={`${s.n} active ${s.n === 1 ? "seller" : "sellers"} from ${money(s.min)} to ${money(s.max)}`} className="h-7 w-full overflow-visible">
            <line x1="0" x2="100%" y1="14" y2="14" className="stroke-border" strokeWidth="1" />
            {s.n > 2 && <rect x={at(s.p25!)} width={`${(x(s.p75!) - x(s.p25!)) * 92}%`} y="8" height="12" rx="2" className="fill-brand-muted" />}
            <line x1={at(s.median!)} x2={at(s.median!)} y1="5" y2="23" className="stroke-muted-foreground" strokeWidth="1.5" />
            {/* Dots draw once on first render (Motion System pattern 15); opacity only, so reduced motion keeps it. */}
            <m.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: duration.base }}>
              {s.points.map((p, i) => (
                <circle key={i} cx={at(p.price_usd_minor)} cy="14" r="3.5" className="fill-foreground stroke-card" strokeWidth="1.5" fillOpacity="0.85">
                  <title>{`${p.domain}: ${money(p.price_usd_minor)}`}</title>
                </circle>
              ))}
            </m.g>
          </svg>
          {s.n > 2 && (
            <p className="flex items-center gap-1.5 text-micro text-subtle-foreground tabular-nums">
              <span aria-hidden className="h-2 w-3 rounded-[2px] bg-brand-muted" />
              Middle 50%: {money(s.p25!)}–{money(s.p75!)}
            </p>
          )}
        </>
      ) : (
        <p className="text-data text-muted-foreground">No USD price from an active seller yet.</p>
      )}
      <Footer asOf={s.as_of} now={now}>
        {s.n} {s.n === 1 ? "seller" : "sellers"}
        {left.length > 0 && `, ${left.join(" and ")} left out`}
      </Footer>
    </section>
  );
}

function SellersTile({ page, now }: { page: Page; now: number }) {
  const { counts, series_90d: days } = page;
  const observed = days.filter((d) => !d.gap).length;
  const segments = sparkSegments(days, 100, 20);
  return (
    <section aria-labelledby="sellers-title" className={tile}>
      <h3 id="sellers-title" className="text-label text-muted-foreground">
        Sellers
      </h3>
      <p className="flex items-baseline gap-2">
        <span className="font-mono text-stat-lg font-semibold text-foreground tabular-nums">{counts.active.toLocaleString("en-US")}</span>
        <span className="text-label text-muted-foreground">active</span>
      </p>
      <p className="text-label text-muted-foreground tabular-nums">
        <span title="Stores Pulso has had for 28 days or more whose listing started in the last 14 days (stable panel)">
          {counts.new_14d} new in 14 d
        </span>{" "}
        · {counts.delisted_30d} delisted in 30 d
      </p>
      {observed > 1 ? (
        <svg role="img" aria-label={`Active sellers per day over 90 days, ${observed} days observed`} viewBox="0 0 100 20" preserveAspectRatio="none" className="h-10 w-full overflow-visible">
          {/* A dashed floor under the whole window, so a gap reads as no data rather than as zero sellers. */}
          <line x1="0" x2="100" y1="20" y2="20" className="stroke-border" strokeWidth="1" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />
          {segments.map((points) =>
            points.includes(" ") ? (
              <polyline key={points} points={points} fill="none" className="stroke-brand" strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            ) : (
              <circle key={points} cx={points.split(",")[0]} cy={points.split(",")[1]} r="1" className="fill-brand" />
            ),
          )}
        </svg>
      ) : (
        <p className="text-data text-muted-foreground">Collecting: {observed} of 90 days observed.</p>
      )}
      <Footer asOf={counts.as_of} now={now}>
        90 d, {90 - observed} gap {90 - observed === 1 ? "day" : "days"}
      </Footer>
    </section>
  );
}

/** No source yet (vault Design/UI States): the band needs the landed-cost engine and a target margin, and the market
 *  range alone is never offered as a suggestion (DEC-247). */
function BandTile() {
  return (
    <section aria-labelledby="band-title" className={cn(tile, "border-dashed border-border")}>
      <h3 id="band-title" className="text-label text-muted-foreground">
        Suggested price
      </h3>
      <p className="flex items-center gap-2 text-body font-medium text-foreground">
        <Calculator className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
        No source yet
      </p>
      <p className="text-data text-muted-foreground">
        The band is where the market&apos;s middle 50% meets the prices that clear your target margin. It needs landed cost (Profit tab) and a target
        margin (Settings), so Pulso won&apos;t suggest a price from the market alone.
      </p>
    </section>
  );
}

export function SummarySkeleton() {
  return (
    <div className="grid gap-3 md:grid-cols-3" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className={tile}>
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-7 w-32" />
          <Skeleton className="h-7 w-full" />
          <Skeleton className="h-3 w-40" />
        </div>
      ))}
    </div>
  );
}
