"use client";

import Link from "next/link";

import { TapTooltip } from "@/components/data-health/atoms";
import { Metric, metricTrigger } from "@/components/pulso/metric";
import type { components } from "@/lib/api/schema";
import { formatDelta, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { StagePill } from "../(pulse)/cards";
import { BestMargin, count, money, Thumb, Velocity, type Column as TableColumn, type Loose } from "../discover/feed-views";
import { COLUMNS, type Column } from "./definition";

type ScreenerRow = components["schemas"]["ScreenerRow"];
export type Row = { [K in keyof ScreenerRow]: Loose<ScreenerRow[K]> };
type Score = Row["trend"];

const DAY = 86_400_000;
const dayOf = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
/** Scored day d reads captures before d+1 00:00Z; 1.5 days past that cutoff it's stale (vault Design/UI States). */
export const scoreStale = (day: string, now: number) => now - Date.parse(day) - DAY > 1.5 * DAY;
const muted = "text-muted-foreground";

/** A value whose card opens on hover, focus and tap, as Metric's does; the label is spoken before it. */
function Hinted({ label, hint, missing, children }: { label: string; hint: React.ReactNode; missing: boolean; children: React.ReactNode }) {
  return (
    <TapTooltip
      hint={
        <div className="flex flex-col gap-1.5 py-0.5">
          <p className="font-medium text-foreground">{label}</p>
          {hint}
        </div>
      }
      side="bottom"
      contentClassName="pointer-events-auto max-w-72 px-3 py-2"
      type="button"
      className={cn(metricTrigger, missing && muted)}
    >
      <span className="sr-only">{label}: </span>
      {children}
    </TapTooltip>
  );
}

/** A stored score (DEC-336 d) as of its scored day (imp-477): no row reads "No source yet", a NULL row "Insufficient
 *  signal" with its reason, never 0 (DEC-040). */
function ScoreCell({ label, score, now, children }: { label: string; score: Score; now: number; children: (s: Extract<Score, { day: string }>) => React.ReactNode }) {
  const row = "day" in score ? score : null;
  const empty = !row ? "No source yet" : row.value == null && row.stage == null ? "Insufficient signal" : null;
  const hint = !row ? (
    <p className={muted}>{score.reason}</p>
  ) : (
    <>
      {row.reason && <p className={muted}>Insufficient signal. {row.reason}</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className={muted}>As of</dt>
        <dd>
          <time dateTime={row.day}>{dayOf.format(new Date(row.day))}</time>, the UTC day scored
          {scoreStale(row.day, now) && <span className="ml-1 text-warning">· Stale</span>}
        </dd>
        <dt className={muted}>Inputs</dt>
        <dd>
          Captured before <time dateTime={row.as_of}>{formatUtc(row.as_of)}</time>
        </dd>
        <dt className={muted}>Source</dt>
        <dd>
          Pulso model <span className="font-mono">{row.model_version}</span>
        </dd>
      </dl>
    </>
  );
  return (
    <Hinted label={label} hint={hint} missing={!!empty}>
      {empty ?? children(row!)}
    </Hinted>
  );
}

function Opportunity({ row }: { row: Row }) {
  const o = row.opportunity;
  const hint = (
    <>
      {o.reason && <p className={muted}>{o.reason}</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className={muted}>As of</dt>
        <dd>{o.as_of ? <time dateTime={o.as_of}>{formatUtc(o.as_of)}</time> : "No inputs yet"}</dd>
        {o.confidence != null && (
          <>
            <dt className={muted}>Confidence</dt>
            <dd className="tabular-nums">{Math.round(o.confidence * 100)}%</dd>
          </>
        )}
        {o.missing.length > 0 && (
          <>
            <dt className={muted}>Missing</dt>
            <dd>{o.missing.join(", ").replaceAll("_", " ")}</dd>
          </>
        )}
        <dt className={muted}>Source</dt>
        <dd>Trend, Saturation and your margin, computed when read</dd>
      </dl>
    </>
  );
  return (
    <Hinted label="Opportunity" hint={hint} missing={o.value == null}>
      {o.value == null ? "Insufficient signal" : o.value.toFixed(0)}
    </Hinted>
  );
}

function Acceleration({ row, now }: { row: Row; now: number }) {
  const a = row.acceleration;
  if (!("source" in a)) return <Metric stat={a} label="Acceleration" missing="Insufficient signal" format={String} now={now} />;
  const delta = formatDelta(a.value, "up", 2);
  const tone = { positive: "text-positive", negative: "text-negative", neutral: muted }[delta.tone];
  const stat = { ...a, raw_payload_id: null, method: `${a.family} family, 7-day growth less the week before's` };
  return <Metric stat={stat} label="Acceleration" format={() => `${delta.glyph ?? ""} ${delta.text}`.trim()} now={now} className={tone} />;
}

function Cell({ row, column, now }: { row: Row; column: Column; now: number }) {
  switch (column) {
    case "lifecycle":
      return (
        <ScoreCell label="Lifecycle" score={row.lifecycle} now={now}>
          {(s) => <StagePill stage={s.stage!} />}
        </ScoreCell>
      );
    case "trend":
    case "saturation":
      return (
        <ScoreCell label={COLUMNS[column]} score={row[column]} now={now}>
          {(s) => s.value!.toFixed(0)}
        </ScoreCell>
      );
    case "opportunity":
      return <Opportunity row={row} />;
    case "velocity":
      return <Velocity item={row} now={now} />;
    case "acceleration":
      return <Acceleration row={row} now={now} />;
    case "margin_bps":
      return <BestMargin item={{ best_margin_minor: row.margin }} now={now} />;
    case "price":
      return <Metric stat={row.price_minor} label="Lowest retail price" format={money} now={now} />;
    case "supplier_rating":
      return <Metric stat={row.supplier_rating} label="Best supplier rating" format={(v) => `${(v / 100).toFixed(1)} ★`} now={now} />;
    case "ship_days_us":
      return <Metric stat={row.ship_days_us} label="Fastest US delivery, worst case" format={(v) => `${count(v)} d`} now={now} />;
  }
}

export const tableColumns = (columns: Column[], now: number): TableColumn<Row>[] =>
  columns.map((key) => ({ name: COLUMNS[key], cell: (row) => <Cell row={row} column={key} now={now} />, className: key === "lifecycle" ? "text-right" : undefined }));

/** Below md, a two-line row (vault UX spec, Responsive): the product, then its first three chosen metrics. The title
 *  link stretches over the row; each metric sits above it and opens its own card. */
export function RowCard({ row, columns, now }: { row: Row; columns: Column[]; now: number }) {
  return (
    <article className="relative flex items-center gap-3 rounded-lg border border-border bg-card p-3 shadow-card has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-2 has-[a:focus-visible]:outline-ring">
      <Thumb url={row.image_url} className="size-10 shrink-0 rounded-md" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h2 className="truncate font-medium text-foreground">
          <Link href={`/products/${row.id}`} className="outline-none after:absolute after:inset-0">
            {row.title}
          </Link>
        </h2>
        <dl className="relative z-10 flex flex-wrap gap-x-4 gap-y-1 text-label">
          {columns.slice(0, 3).map((key) => (
            <div key={key} className="flex items-center gap-1.5">
              <dt className="text-subtle-foreground">{COLUMNS[key]}</dt>
              <dd>
                <Cell row={row} column={key} now={now} />
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </article>
  );
}
