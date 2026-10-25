"use client";

import Link from "next/link";
import { CircleOff, GitMerge, Mountain, Sprout, TrendingDown, TrendingUp, type LucideIcon } from "lucide-react";

import { TapTooltip } from "@/components/data-health/atoms";
import { Metric } from "@/components/pulso/metric";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { freshness, marginText, money, scoreText, STAGES, type Item, type Score, type Stage } from "../model";

// A card's stats (imp-454) in the vault card's order: price range, best landed margin, Trend, Lifecycle, Saturation.
// Each opens where it came from on hover, focus and tap; one nothing backs reads "No source yet", never 0 (DEC-040).

export function Price({ item, now }: { item: Item; now: number }) {
  const [low, high] = [item.price_min_minor, item.price_max_minor];
  if ("reason" in low || "reason" in high || low.value === high.value) return <Metric stat={low} label="Retail price" format={money} now={now} />;
  return (
    <span className="whitespace-nowrap">
      <Metric stat={low} label="Lowest retail price" format={money} now={now} />
      <span aria-hidden className="mx-0.5 text-subtle-foreground">–</span>
      <Metric stat={high} label="Highest retail price" format={money} now={now} />
    </span>
  );
}

export function Margin({ item, now }: { item: Item; now: number }) {
  const margin = item.best_margin_minor;
  const text = marginText(margin);
  return <Metric stat={margin} label="Best landed margin" format={() => text} missing={text} now={now} className={cn("whitespace-nowrap", text === "Duty not set" && "text-warning")} />;
}

const trigger = "relative hit-area cursor-help rounded-sm tabular-nums decoration-border-strong decoration-dotted underline-offset-4 hover:underline";

export function ScoreValue({ score, label, now }: { score: Score; label: string; now: number }) {
  const text = scoreText(score);
  return (
    <TapTooltip
      hint={<ScoreCard score={score} label={label} now={now} />}
      side="bottom"
      contentClassName="pointer-events-auto max-w-72 px-3 py-2"
      type="button"
      aria-label={`${label}: ${text}`}
      className={cn(trigger, "whitespace-nowrap", !/^\d/.test(text) && "text-muted-foreground")}
    >
      {text}
    </TapTooltip>
  );
}

// Colours per vault Intelligence/Lifecycle Stage; the label and icon carry the stage, never colour alone.
const CHIPS: Record<Stage, { icon: LucideIcon; tone: string }> = {
  emerging: { icon: Sprout, tone: "bg-positive-muted text-positive" },
  rising: { icon: TrendingUp, tone: "bg-positive-muted text-positive" },
  peaking: { icon: Mountain, tone: "bg-warning-muted text-warning" },
  declining: { icon: TrendingDown, tone: "bg-negative-muted text-negative" },
  dead: { icon: CircleOff, tone: "border border-dashed border-border-strong text-subtle-foreground" },
};

/** The Lifecycle chip; without a stage, the score's words ("Insufficient signal", "No source yet"). */
export function Lifecycle({ item, now }: { item: Item; now: number }) {
  const score = item.lifecycle;
  const stage = "model_version" in score ? score.stage : null;
  if (!stage) return <ScoreValue score={score} label="Lifecycle stage" now={now} />;
  const { icon: Icon, tone } = CHIPS[stage];
  return (
    <TapTooltip
      hint={<ScoreCard score={score} label="Lifecycle stage" now={now} />}
      side="bottom"
      contentClassName="pointer-events-auto max-w-72 px-3 py-2"
      type="button"
      aria-label={`Lifecycle stage: ${STAGES[stage]}`}
      className={cn("relative hit-area inline-flex h-5.5 cursor-help items-center gap-1 rounded-sm px-1.5 text-label font-medium whitespace-nowrap", tone)}
    >
      <Icon className="size-3.5" aria-hidden />
      {STAGES[stage]}
    </TapTooltip>
  );
}

/** A score's provenance: Pulso's own model, the UTC day scored and when its inputs were captured (DEC-331). */
function ScoreCard({ score, label, now }: { score: Score; label: string; now: number }) {
  return (
    <div className="flex flex-col gap-1.5 py-0.5">
      <p className="font-medium text-foreground">{label}</p>
      {!("model_version" in score) ? (
        <p className="text-muted-foreground">{score.reason}</p>
      ) : (
        <>
          {score.reason && <p className="text-muted-foreground">Insufficient signal: {score.reason}.</p>}
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted-foreground">Source</dt>
            <dd>
              Pulso score · <span className="font-mono">{score.model_version}</span>
            </dd>
            <dt className="text-muted-foreground">Scored</dt>
            <dd>{score.day} (UTC day)</dd>
            <dt className="text-muted-foreground">As of</dt>
            <dd>
              <time dateTime={score.as_of}>{formatUtc(score.as_of)}</time> · {formatAgo(score.as_of, now)}
            </dd>
          </dl>
        </>
      )}
    </div>
  );
}

/** The grid card's stats, labels left and numbers right in tabular numerals. */
export function StatList({ item, now }: { item: Item; now: number }) {
  const rows: [string, React.ReactNode][] = [
    ["Price", <Price key="p" item={item} now={now} />],
    ["Best margin", <Margin key="m" item={item} now={now} />],
    ["Trend", <ScoreValue key="t" score={item.trend} label="Trend Score" now={now} />],
    ["Lifecycle", <Lifecycle key="l" item={item} now={now} />],
    ["Saturation", <ScoreValue key="s" score={item.saturation} label="Saturation" now={now} />],
  ];
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1 border-t border-border-subtle pt-2 text-data">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-label text-subtle-foreground">{label}</dt>
          <dd className="flex min-h-5.5 items-center justify-end text-right">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The oldest stat's age; amber with "stale" when a traced stat is past twice its source's interval. */
export function Freshness({ item, now }: { item: Item; now: number }) {
  const { as_of, stale } = freshness(item);
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-subtle-foreground">
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", stale ? "bg-warning" : "bg-border-strong")} />
      {as_of ? (
        <time dateTime={as_of} title={`Oldest stat on this card: ${formatUtc(as_of)}`}>
          {formatAgo(as_of, now)}
        </time>
      ) : (
        "Not collected yet"
      )}
      {stale && <span className="text-warning">· stale</span>}
    </span>
  );
}

/** A product merged after it was added: the card keeps it, shows the survivor's stats and says so (DEC-319 e). */
export function Merged({ item }: { item: Item }) {
  if (!item.merged_into_id) return null;
  return (
    <p className="flex items-start gap-1.5 rounded-md bg-info/12 px-2 py-1 text-label text-info">
      <GitMerge className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>
        Merged into another product; its stats show here.{" "}
        <Link href={`/products/${item.merged_into_id}`} className="relative hit-area rounded-sm font-medium whitespace-nowrap underline underline-offset-2">
          Open it<span className="sr-only">: the product {item.name} became</span>
        </Link>
      </span>
    </p>
  );
}
