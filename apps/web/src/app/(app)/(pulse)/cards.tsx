"use client";

import { useState } from "react";
import Link from "next/link";
import * as m from "motion/react-m";
import {
  ArrowRight,
  Bell,
  CircleDashed,
  CircleOff,
  Mountain,
  Package,
  PackageCheck,
  PackageX,
  Percent,
  Search,
  Sprout,
  Star,
  Store,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import { Segmented } from "@/app/(app)/boards/parts";
import { Thumb } from "@/app/(app)/discover/feed-views";
import { money } from "@/app/(app)/products/[id]/profit/model";
import { describeAlert, entityHref, TYPES } from "@/components/alerts/model";
import { TapTooltip } from "@/components/data-health/atoms";
import { DeltaBadge } from "@/components/pulso/delta-badge";
import { EmptyState } from "@/components/pulso/empty-state";
import { Sparkline } from "@/components/pulso/sparkline";
import { StatusDot } from "@/components/pulso/status-dot";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { GoodDirection } from "@/lib/format";
import { duration, ease, stagger } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { isStale, sectionOf, seriesValues, sourceNames, type CardId, type Pulse } from "./model";

type Stage = Pulse["sections"]["emerging"]["items"][number]["stage"];

const CARDS: Record<CardId, { title: string; icon: LucideIcon; empty: string; beta?: boolean }> = {
  emerging: { title: "Top emerging", icon: Sprout, empty: "No emerging products", beta: true },
  movers: { title: "Biggest movers", icon: TrendingUp, empty: "No movers", beta: true },
  new_in_stores: { title: "New in tracked stores", icon: Store, empty: "No launches" },
  alerts: { title: "Alerts", icon: Bell, empty: "No alerts fired" },
  watchlists: { title: "Watchlist", icon: Star, empty: "Nothing watched yet" },
  suppliers: { title: "Supplier changes", icon: Package, empty: "No supplier changes" },
  search: { title: "Search movers", icon: Search, empty: "No search movers" },
  margins: { title: "Margin changes", icon: Percent, empty: "No margin changes" },
};

// Vault Design/Component Inventory, LifecyclePill: icon, label and colour, never colour alone.
const STAGES: Record<Stage, [LucideIcon, string, string]> = {
  emerging: [Sprout, "Emerging", "border-positive/40 bg-positive-muted text-positive"],
  rising: [TrendingUp, "Rising", "border-border text-positive"],
  peaking: [Mountain, "Peaking", "border-border text-warning"],
  declining: [TrendingDown, "Declining", "border-border text-negative"],
  dead: [CircleOff, "Dead", "border-border text-muted-foreground"],
};

const utcTime = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" });
const utcDate = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
/** A time on the pulse's own day reads as its UTC clock time, any other as its date. */
const when = (iso: string, day: string) => (iso.slice(0, 10) === day ? `${utcTime.format(new Date(iso))} UTC` : utcDate.format(new Date(iso)));
const stamp = (iso: string, source: string) => `${source} · as of ${utcDate.format(new Date(iso))}, ${utcTime.format(new Date(iso))} UTC`;
const product = (id: string, tab?: string) => `/products/${id}${tab ? `?tab=${tab}` : ""}`;
const pct = (bps: number) => `${(bps / 100).toFixed(1)}%`;

// One card per section (vault Features/Daily Pulse): its own as of and sources, and a designed state per status. The
// cards stagger in once per session (Motion System pattern 16); rows never animate.
export function PulseCard({ id, pulse, index, animate }: { id: CardId; pulse: Pulse; index: number; animate: boolean }) {
  const [down, setDown] = useState(false);
  const [listId, setListId] = useState<string>();
  const { sections } = pulse;
  const card = CARDS[id];
  const section = id === "movers" && down ? sections.movers_down : sectionOf(sections, id);
  const lists = sections.watchlists.items;
  const list = lists.find((l) => l.id === listId) ?? lists[0];
  const fed = section.status !== "no_source";
  const control = "h-(--input-h) rounded-md border border-border bg-secondary px-2 text-label text-foreground hover:border-border-strong";

  return (
    <m.section
      aria-labelledby={`pulse-${id}`}
      data-status={section.status}
      className={cn("flex min-w-0 flex-col rounded-xl border bg-card shadow-card", fed ? "border-border" : "border-dashed border-border-strong")}
      initial={animate ? { opacity: 0, y: 8 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.base, ease: ease.out, delay: Math.min(index, stagger.max) * stagger.step }}
    >
      <header className="flex min-h-12 flex-wrap items-center gap-x-2 gap-y-1 border-b border-border-subtle px-4 py-2">
        <card.icon className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
        <h2 id={`pulse-${id}`} className="text-title-3 font-semibold text-foreground">
          {card.title}
        </h2>
        {card.beta && <span className="inline-flex h-5 items-center rounded-sm border border-border px-1.5 text-micro font-medium text-muted-foreground">Beta</span>}
        {id === "alerts" && sections.alerts.unread > 0 && (
          <span className="inline-flex h-5 items-center rounded-full bg-brand-muted px-2 text-micro font-medium text-foreground tabular-nums">{sections.alerts.unread} unread</span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {id === "movers" && fed && (
            <Segmented
              id="pulse-movers"
              label="Movers direction"
              value={down ? "down" : "up"}
              options={[
                { value: "up", label: "Up", icon: TrendingUp },
                { value: "down", label: "Down", icon: TrendingDown },
              ]}
              onChange={(v) => setDown(v === "down")}
            />
          )}
          {id === "watchlists" && lists.length > 1 && (
            <select aria-label="Watchlist" className={control} value={list?.id} onChange={(e) => setListId(e.target.value)}>
              {lists.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} ({l.item_count})
                </option>
              ))}
            </select>
          )}
          <AsOf asOf={section.as_of} sources={section.sources} pulse={pulse} />
        </div>
      </header>
      {section.status === "ok" ? (
        <ul className="flex flex-col py-1 zone-data">{rows(id, pulse, down, list)}</ul>
      ) : fed ? (
        <EmptyState
          icon={card.icon}
          title={card.empty}
          size="sm"
          className="flex-1 justify-center"
          action={
            id === "watchlists" && (
              <Button asChild size="sm" variant="ghost">
                <Link href="/discover">Find products in Discover</Link>
              </Button>
            )
          }
        >
          {section.reason}
        </EmptyState>
      ) : (
        // No source (DEC-040): a status line, never zeros, so a source that is off takes little room.
        <p className="flex flex-1 items-start gap-2.5 px-4 py-4 text-data text-muted-foreground">
          <CircleDashed className="mt-0.5 size-4 shrink-0 text-subtle-foreground" strokeWidth={1.5} aria-hidden />
          <span>
            <span className="font-medium text-foreground">No source yet.</span> {section.reason}{" "}
            <Link href="/admin/data-health" className="relative hit-area rounded-sm font-medium whitespace-nowrap text-foreground underline underline-offset-4">
              Open Data Health
            </Link>
          </span>
        </p>
      )}
      {(id === "alerts" || (id === "watchlists" && list)) && (
        <Link
          href={id === "alerts" ? "/alerts" : `/watchlists?list=${list!.id}`}
          className="relative hit-area mt-auto flex h-10 items-center gap-1.5 rounded-b-xl border-t border-border-subtle px-4 text-label font-medium text-muted-foreground transition-colors duration-(--duration-fast) hover:text-foreground"
        >
          {id === "alerts" ? "Open the alerts inbox" : `Open ${list!.name}`}
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      )}
    </m.section>
  );
}

function rows(id: CardId, pulse: Pulse, down: boolean, list: Pulse["sections"]["watchlists"]["items"][number] | undefined) {
  const { sections, day } = pulse;
  const thumb = (url: string | null | undefined) => <Thumb url={url ?? null} className="size-6 shrink-0 rounded-sm" />;
  switch (id) {
    case "emerging":
      return sections.emerging.items.map((e) => (
        <Row key={e.product.id} href={product(e.product.id)} lead={thumb(e.product.image_url)} name={e.product.name} title={stamp(e.as_of, "Trend Score")}>
          <StagePill stage={e.stage} neutral className="max-sm:hidden" />
          <span className="w-10 text-right text-foreground">{e.value.toFixed(1)}</span>
          <Delta value={e.since_yesterday?.change} missing="No comparable score the day before" />
        </Row>
      ));
    case "movers":
      return (down ? sections.movers_down : sections.movers_up).items.map((mv) => (
        <Row key={mv.product.id} href={product(mv.product.id)} lead={thumb(mv.product.image_url)} name={mv.product.name} title={stamp(mv.as_of, "Trend Score")}>
          <span className="text-muted-foreground max-sm:hidden">
            {mv.old.toFixed(1)} → {mv.new.toFixed(1)}
          </span>
          <Delta value={mv.change} />
        </Row>
      ));
    case "new_in_stores":
      return sections.new_in_stores.items.map((l) => (
        <Row key={l.listing_id} href={l.product && product(l.product.id, "sellers")} lead={thumb(l.product?.image_url)} name={l.title} title={stamp(l.as_of, "Shopify stores")}>
          <span className="max-w-32 truncate text-muted-foreground max-sm:hidden">{l.store}</span>
          <span className="text-muted-foreground">{when(l.published_at, day)}</span>
        </Row>
      ));
    case "alerts":
      return sections.alerts.items.map((a) => {
        const d = describeAlert(a);
        return (
          <Row
            key={a.id}
            href={entityHref(a)}
            lead={
              <>
                <span aria-hidden className={cn("size-2 shrink-0 rounded-full bg-brand", a.read_at && "opacity-0")} />
                <d.icon className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
              </>
            }
            name={d.title}
            unread={!a.read_at}
            title={d.asOf ? `${d.meta} · as of ${when(d.asOf, day)}` : d.meta}
          >
            {d.pct !== null && <Delta value={d.pct} good="down" unit="%" />}
            <time dateTime={a.fired_at} className="text-muted-foreground">
              {when(a.fired_at, day)}
            </time>
          </Row>
        );
      });
    case "watchlists":
      return list?.items.map((w) => (
        <Row key={w.product.id} href={product(w.product.id)} lead={thumb(w.product.image_url)} name={w.product.name} title={w.series.at(-1) && stamp(w.series.at(-1)!.as_of, "Trend Score")}>
          {[...new Set(w.alerts)].map((type) => (
            <span key={type} className="inline-flex h-5 items-center rounded-sm border border-border px-1.5 text-micro text-muted-foreground max-md:hidden">
              {TYPES[type]?.label ?? type}
            </span>
          ))}
          <Sparkline values={seriesValues(w.series, day)} />
          {w.stage && <StagePill stage={w.stage} from={w.stage_before !== w.stage ? w.stage_before : null} className="max-sm:hidden" />}
          <Delta value={w.trend?.change} missing="No comparable score the day before" />
        </Row>
      ));
    case "suppliers":
      return sections.suppliers.items.map((s) => (
        <Row key={s.listing_id} href={s.product && product(s.product.id, "suppliers")} lead={thumb(s.product?.image_url)} name={s.title} title={stamp(s.as_of, sourceNames([s.source]))}>
          {s.in_stock !== null && (
            <span className={cn("inline-flex items-center gap-1", s.in_stock ? "text-positive" : "text-negative")}>
              {s.in_stock ? <PackageCheck className="size-3.5" aria-hidden /> : <PackageX className="size-3.5" aria-hidden />}
              {s.in_stock ? "Back in stock" : "Out of stock"}
            </span>
          )}
          {s.price_change_pct !== null && (
            <>
              <span className="text-muted-foreground max-sm:hidden">
                {money(s.old_price_minor!, s.currency ?? "USD")} → {money(s.new_price_minor!, s.currency ?? "USD")}
              </span>
              <Delta value={s.price_change_pct} good="down" unit="%" />
            </>
          )}
        </Row>
      ));
    case "search":
      return sections.search.items.map((s) => (
        <Row key={s.product.id} href={product(s.product.id, "trends")} lead={thumb(s.product.image_url)} name={s.product.name} title={stamp(s.as_of, "Google Trends")}>
          <span className="text-muted-foreground max-sm:hidden">
            {s.keywords} {s.keywords === 1 ? "keyword" : "keywords"}
          </span>
          <Delta value={s.change_pct} unit="%" />
        </Row>
      ));
    case "margins":
      return sections.margins.items.map((mg) => (
        <Row key={mg.product.id} href={product(mg.product.id, "profit")} lead={thumb(mg.product.image_url)} name={mg.product.name} title={stamp(mg.as_of, "Landed cost")}>
          {mg.duty_not_set && (
            <span title="Costed at duty 0: set a duty rate in Settings" className="text-micro text-warning max-sm:hidden">
              Duty not set
            </span>
          )}
          <span className="text-muted-foreground max-sm:hidden">
            {pct(mg.old_bps)} → {pct(mg.new_bps)}
          </span>
          <Delta value={mg.change_bps / 100} unit=" pp" />
        </Row>
      ));
  }
}

/** A list row, 32 px (44 on touch). The whole row opens the item; its title says each number's source and as of. */
function Row({ href, lead, name, unread, title, children }: { href: string | null; lead: React.ReactNode; name: string; unread?: boolean; title?: string; children: React.ReactNode }) {
  const label = cn("min-w-0 flex-1 truncate", unread === false ? "text-muted-foreground" : "text-foreground", unread && "font-medium");
  return (
    <li className="relative flex h-(--table-row-h) items-center gap-3 px-4 hover:bg-(--table-row-hover)">
      {lead}
      {href ? (
        <Link href={href} title={title} className={cn(label, "rounded-sm after:absolute after:inset-0 hover:underline")}>
          {unread && <span className="sr-only">Unread: </span>}
          {name}
        </Link>
      ) : (
        <span title={title} className={label}>
          {name}
        </span>
      )}
      <span className="flex shrink-0 items-center gap-3 tabular-nums">{children}</span>
    </li>
  );
}

function Delta({ value, good = "up", unit, missing }: { value: number | null | undefined; good?: GoodDirection; unit?: string; missing?: string }) {
  return <DeltaBadge value={value} goodDirection={good} unit={unit} missingReason={missing} className="min-w-14 justify-end" />;
}

/** `neutral` where every row shares a stage (Top emerging), so colour marks only the rows that differ. */
export function StagePill({ stage, from, neutral, className }: { stage: Stage; from?: Stage | null; neutral?: boolean; className?: string }) {
  const [Icon, label, tone] = STAGES[stage];
  return (
    <span
      title={from ? `Entered ${label} on this day, from ${STAGES[from][1]}` : undefined}
      className={cn("inline-flex h-5.5 items-center gap-1 rounded-sm border px-1.5 text-label font-medium whitespace-nowrap", neutral ? "border-border text-muted-foreground" : tone, className)}
    >
      <Icon className="size-3.5" aria-hidden />
      {label}
      {from && <span className="sr-only">, entered on this day from {STAGES[from][1]}</span>}
      {from && <span aria-hidden className="size-1.5 rounded-full bg-current" />}
    </span>
  );
}

/** The card's as of with its sources on hover, keyboard focus and tap. Stale (older than 1.5 days before the day's
 *  cutoff) adds an amber dot and says so. */
function AsOf({ asOf, sources, pulse }: { asOf: string | null; sources: string[]; pulse: Pulse }) {
  const stale = isStale(asOf, pulse.cutoff);
  return (
    <TapTooltip
      type="button"
      side="bottom"
      hint={
        <span className="flex flex-col gap-0.5">
          <span>{asOf ? stamp(asOf, "Newest input") : "Nothing captured for this day"}</span>
          <span className="text-muted-foreground">Sources: {sourceNames(sources)}</span>
          {stale && <span className="text-warning">Stale: older than 36 h when the day closed</span>}
        </span>
      }
      className="relative hit-area inline-flex items-center gap-1.5 rounded-sm text-label whitespace-nowrap text-subtle-foreground hover:text-foreground"
    >
      {stale && <StatusDot state="warning" />}
      {stale && <span className="sr-only">Stale,</span>}
      As of {asOf ? when(asOf, pulse.day) : "—"}
    </TapTooltip>
  );
}

/** The eight cards in their loaded anatomy, a header and five 32 px rows each (vault Design/UI States, Loading). */
export function CardsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6">
      <span className="sr-only" role="status">
        Loading Daily Pulse
      </span>
      {Object.keys(CARDS).map((id) => (
        <div key={id} aria-hidden className="flex flex-col rounded-xl border border-border bg-card shadow-card">
          <div className="flex h-12 items-center gap-2 border-b border-border-subtle px-4">
            <Skeleton className="h-4 w-36" />
            <Skeleton className="ml-auto h-3 w-20" />
          </div>
          <div className="flex flex-col py-1">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className="flex h-(--table-row-h) items-center gap-3 px-4">
                <Skeleton className="size-6" />
                <Skeleton className="h-3.5 max-w-56 flex-1" />
                <Skeleton className="ml-auto h-3.5 w-12" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
