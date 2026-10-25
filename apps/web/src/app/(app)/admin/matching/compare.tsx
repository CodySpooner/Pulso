"use client";

import { useState } from "react";
import Link from "next/link";
import * as m from "motion/react-m";
import { ExternalLink, ImageOff, Package } from "lucide-react";

import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import type { components } from "@/lib/api/schema";
import { formatAgo, formatUtc } from "@/lib/format";
import { duration, ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { bars, isGtin, money, sourceLabel, type Cluster, type Detail } from "./model";

type ListingDetail = components["schemas"]["ListingDetail"];

const pct = (value: number) => `${(value * 100).toFixed(0)}%`;
const score = (value: number) => value.toFixed(2);

/** A listing image, or a placeholder that says why there is none. The decision never needs the image. */
export function Thumb({ url, className, label }: { url: string | null | undefined; className?: string; label?: string }) {
  const [broken, setBroken] = useState<string | null>(null);
  if (!url || broken === url)
    return (
      <div className={cn("grid place-items-center gap-1 bg-secondary text-center text-subtle-foreground", className)}>
        {label ? (
          <span className="flex flex-col items-center gap-1 px-2 text-label">
            <ImageOff className="size-5" strokeWidth={1.5} aria-hidden />
            {url ? "Image unavailable" : "No image stored"}
          </span>
        ) : (
          <Package className="size-1/3 max-h-6 max-w-6" strokeWidth={1.5} aria-hidden />
        )}
      </div>
    );
  // eslint-disable-next-line @next/next/no-img-element -- listing images come from any store or supplier CDN; next/image would need each host allow-listed
  return <img src={url} alt={label ?? ""} decoding="async" onError={() => setBroken(url)} className={cn("bg-secondary object-contain", className)} />;
}

function Side({ side, image, label, now }: { side: ListingDetail; image: number; label: "A" | "B"; now: number }) {
  const shown = Math.min(image, Math.max(side.images.length - 1, 0));
  return (
    <article aria-label={`Listing ${label}: ${side.title}`} className="flex min-w-0 flex-col gap-3">
      <div className="relative overflow-hidden rounded-lg border border-border">
        <Thumb url={side.images[shown]} label={side.title} className="aspect-square w-full" />
        <span className="absolute top-2 left-2 rounded-sm bg-card/90 px-1.5 py-0.5 text-micro font-medium text-muted-foreground">{label}</span>
      </div>
      {side.images.length > 1 && (
        <div className="flex gap-1.5" aria-label="Gallery">
          {side.images.map((url, i) => (
            <span key={url} className={cn("relative size-11 overflow-hidden rounded-md border", i === shown ? "border-foreground" : "border-border")}>
              <Thumb url={url} className="size-full" />
              <Kbd className="absolute right-0.5 bottom-0.5 h-4 min-w-4 px-1">{i + 1}</Kbd>
              <span className="sr-only">{i === shown ? `Image ${i + 1}, shown` : `Image ${i + 1}`}</span>
            </span>
          ))}
        </div>
      )}
      <div className="flex min-w-0 flex-col gap-1">
        <a href={side.url} target="_blank" rel="noopener noreferrer" className="group inline-flex min-w-0 items-start gap-1 text-body font-medium text-foreground">
          <span className="line-clamp-2 group-hover:underline">{side.title}</span>
          <ExternalLink className="mt-0.5 size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
          <span className="sr-only">(opens the {side.source_name} page)</span>
        </a>
        <p className="truncate text-label text-muted-foreground">
          {side.source_name}
          {side.vendor && <> · {side.vendor}</>}
          {side.delisted_at && <span className="text-warning"> · delisted {formatUtc(side.delisted_at)}</span>}
        </p>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-data">
        <dt className="text-muted-foreground">Price</dt>
        <dd className="text-right font-mono tabular-nums text-foreground">
          {side.price?.min_minor != null ? (
            <span title={`${side.source_name}, captured ${formatUtc(side.price.captured_at)}`}>
              {money(side.price.min_minor, side.price.currency)}
              {side.price.max_minor != null && side.price.max_minor !== side.price.min_minor && <>–{money(side.price.max_minor, side.price.currency)}</>}
              <span className="block text-micro font-sans text-subtle-foreground">as of {formatAgo(side.price.captured_at, now)}</span>
            </span>
          ) : (
            <span className="font-sans text-subtle-foreground">No price captured yet</span>
          )}
        </dd>
        <dt className="text-muted-foreground">Variants</dt>
        <dd className="text-right font-mono tabular-nums">{side.variants}</dd>
        <dt className="text-muted-foreground">First seen</dt>
        <dd className="text-right" title={formatUtc(side.first_seen_at)}>
          {formatAgo(side.first_seen_at, now)}
        </dd>
        <dt className="text-muted-foreground">Product</dt>
        <dd className="truncate text-right">
          {side.product_id ? (
            <Link href={`/products/${side.product_id}`} className="text-info hover:underline">
              Open product
            </Link>
          ) : (
            <span className="text-subtle-foreground">None yet</span>
          )}
        </dd>
      </dl>
    </article>
  );
}

function ScoreBar({ label, value, weight, missing, ticks, strong }: { label: string; value: number | null; weight?: number; missing?: string; ticks?: number[]; strong?: boolean }) {
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr_3.5rem] items-center gap-3 text-data">
      <span className={cn("truncate", strong ? "font-medium text-foreground" : "text-muted-foreground")}>
        {label}
        {weight != null && <span className="ml-1 text-micro text-subtle-foreground">×{weight.toFixed(2)}</span>}
      </span>
      <div className="relative h-1.5 rounded-full bg-secondary" aria-hidden>
        {value != null && (
          <m.div
            className={cn("absolute inset-y-0 left-0 origin-left rounded-full", strong ? "bg-brand" : "bg-muted-foreground")}
            style={{ width: pct(value) }}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: duration.fast, ease: ease.out }}
          />
        )}
        {ticks?.map((tick) => (
          <span key={tick} className="absolute -inset-y-1 w-px bg-foreground/60" style={{ left: pct(tick) }} />
        ))}
      </div>
      <span className={cn("text-right font-mono tabular-nums", value == null ? "text-subtle-foreground" : "text-foreground")} title={value == null ? missing : undefined}>
        {value == null ? "n/a" : score(value)}
        {value == null && <span className="sr-only">: {missing}</span>}
      </span>
    </div>
  );
}

function Scores({ detail }: { detail: Detail }) {
  const t = detail.thresholds;
  const price = detail.price_sane;
  return (
    <section aria-labelledby="scores-title" className="flex flex-col gap-2.5 rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="scores-title" className="text-title-3 font-semibold">
          Score
        </h3>
        <p className="text-label text-subtle-foreground">
          {isGtin(detail.scorer_version) ? "Shared GTIN: linked at 1.00" : `Auto-link ≥ ${score(t.auto_link)} · queue ≥ ${score(t.queue)}`} ·{" "}
          <span className="font-mono">{detail.scorer_version}</span>
          {!isGtin(detail.scorer_version) && detail.scorer_version !== t.version && <span className="text-warning"> · scored by an older version</span>}
        </p>
      </div>
      <ScoreBar label="Combined" value={detail.score} ticks={[t.queue, t.auto_link]} strong />
      {bars(detail).map((bar) => (
        <ScoreBar key={bar.id} {...bar} />
      ))}
      <div className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 text-data">
        <span className="text-muted-foreground">Price check</span>
        <span className={cn("text-right", price === false ? "text-warning" : price ? "text-foreground" : "text-subtle-foreground")}>
          {price == null
            ? "n/a: a price or rate is missing"
            : price
              ? `${score(t.markup_low)}–${score(t.markup_high)}× markup band ✓`
              : `Outside the ${score(t.markup_low)}–${score(t.markup_high)}× band ✕ (never auto-links)`}
        </span>
      </div>
    </section>
  );
}

/** The cluster strip: the side's product and its current members, so a listing that doesn't fit stands out. */
function ClusterStrip({ clusters }: { clusters: Cluster[] }) {
  if (clusters.length === 0)
    return <p className="text-data text-muted-foreground">Neither listing is on a product yet. Accept makes a new product named after the older listing.</p>;
  return (
    <div className="flex flex-col gap-3">
      {clusters.map((c) => (
        <section key={c.product_id} aria-label={`Product ${c.name}`} className="flex min-w-0 flex-col gap-2">
          <p className="flex flex-wrap items-baseline gap-x-2 text-data">
            <Link href={`/products/${c.product_id}`} className="max-w-full truncate font-medium text-foreground hover:underline">
              {c.name}
            </Link>
            <span className="text-label text-subtle-foreground">
              {c.listings} {c.listings === 1 ? "listing" : "listings"} · {c.notes} {c.notes === 1 ? "note" : "notes"} · {c.tags} {c.tags === 1 ? "tag" : "tags"}
            </span>
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {c.members.slice(0, 12).map((member) => (
              <li key={member.listing_id} title={`${member.title} · ${sourceLabel(member.source)}${member.vendor ? ` · ${member.vendor}` : ""}`}>
                <Thumb url={member.image_url} className="size-10 rounded-md border border-border" />
                <span className="sr-only">{member.title}</span>
              </li>
            ))}
            {c.listings > 12 && <li className="grid size-10 place-items-center rounded-md border border-dashed border-border-strong text-label text-muted-foreground">+{c.listings - 12}</li>}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** One pair side by side. It enters with a fade only and never exits, so no keypress waits for it. */
export function Compare({ detail, image, now }: { detail: Detail; image: number; now: number }) {
  return (
    <m.div
      key={detail.id}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: duration.base, ease: ease.out }}
      className="flex flex-col gap-4"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Side side={detail.a} image={image} label="A" now={now} />
        <Side side={detail.b} image={image} label="B" now={now} />
      </div>
      <Scores detail={detail} />
      <section aria-labelledby="cluster-title" className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
        <h3 id="cluster-title" className="text-title-3 font-semibold">
          Products
        </h3>
        <ClusterStrip clusters={detail.clusters} />
      </section>
    </m.div>
  );
}

export function CompareSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-hidden>
      <div className="grid gap-4 sm:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i} className="flex flex-col gap-3">
            <Skeleton className="aspect-square w-full rounded-lg" />
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="grid grid-cols-[9rem_1fr_3.5rem] items-center gap-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-1.5 w-full rounded-full" />
            <Skeleton className="h-3 w-10 justify-self-end" />
          </div>
        ))}
      </div>
    </div>
  );
}
