"use client";

import { useEffect } from "react";
import Link from "next/link";
import { TriangleAlert } from "lucide-react";

import { StagePill } from "@/app/(app)/(pulse)/cards";
import { isBuilt, methodology } from "@/app/(app)/methodology/model";
import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine, TapTooltip } from "@/components/data-health/atoms";
import { BetaPill, MissingInputs, ScoreExplanation } from "@/components/pulso/score-explanation";
import { chips, unscored, unscoredOpportunity, type Explanation, type ScoreKind } from "@/components/pulso/score-model";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { card } from "./stat-card";

type Stored = components["schemas"]["StoredScore"];
type Latest = Stored | { reason: string; value?: null };

const date = (iso: string) => new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(iso));
const STALE_MS = 3 * 86_400_000; // 3 × the nightly cadence (vault Score Definitions §7)
const link = "relative hit-area rounded-sm text-muted-foreground underline decoration-border-strong underline-offset-2 hover:text-foreground hover:decoration-current";
const chip = "inline-flex h-5 items-center gap-1 rounded-sm border px-1.5 text-micro font-medium text-foreground";

// Saturation's bands from its config in the /methodology export, so a config change can't leave them behind.
const saturation = methodology.scores.find((s) => s.id === "saturation");
const band = Object.fromEntries((saturation && isBuilt(saturation) ? saturation.config : []).map((c) => [c.name, Number(c.value)]));
const crowding = (v: number) => (v < band.low_below ? "Low" : v > band.high_above ? "High" : "Medium");

/** SC-5 / WF-1 (imp-460): Trend, Opportunity, Saturation and Lifecycle from GET /v1/products/{id}/scores, behind
 *  ff_scores. Its own request, so its skeleton, error and stale line never hold up the key stats. */
export function ScoreCards({ id }: { id: string }) {
  const query = $api.useQuery(
    "get",
    "/v1/products/{product_id}/scores",
    { params: { path: { product_id: id }, query: { range: "7d", limit: 1 } } }, // the latest rows; history isn't shown
    { enabled: useApiReady(), retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1 },
  );
  const { data, error } = query;
  const retry = () => void query.refetch();
  // Discover's Trend cell links to #score-trend, which didn't exist when the page loaded: land on it once it does.
  useEffect(() => {
    const target = data && document.getElementById(window.location.hash.slice(1));
    if (!target?.hasAttribute("data-score")) return;
    target.scrollIntoView({ block: "center" });
    target.focus({ preventScroll: true });
  }, [data]);
  if (!data)
    return query.isError ? (
      <section className={card}>
        <PanelError headingLevel="h2" title="Couldn't load the scores" error={error} retry={retry} />
      </section>
    ) : (
      <ScoresSkeleton />
    );

  const now = query.dataUpdatedAt;
  const { latest, opportunity } = data;
  const o = opportunity.explanation;
  return (
    <section aria-labelledby="scores-title" className="flex flex-col gap-3">
      <h2 id="scores-title" className="sr-only">
        Scores
      </h2>
      {query.isError && <StaleLine boxed what="Couldn't refresh the scores" error={error} asOf={now} retry={retry} />}
      <div className="grid gap-3 sm:grid-cols-2 3xl:grid-cols-4">
        <Numeric kind="trend" title="Trend Score" anchor="trend-score" latest={latest.trend} now={now} />
        <Card
          kind="opportunity"
          title="Opportunity"
          // DEC-331 a: Momentum is Trend Score v0 until a forecast is published, and the pill says so.
          beta={o.components.some((c) => c.name === "trend")}
          anchor="opportunity"
          asOf={
            opportunity.as_of && (
              // Not a stored row, so no scored day: the time of its oldest input.
              <AsOf at={opportunity.as_of} now={now} text={`As of ${formatUtc(opportunity.as_of)}`} hint="Computed for your workspace when the page loaded, from its oldest input's time. Never stored." />
            )
          }
        >
          <Value
            missing={unscoredOpportunity(opportunity.value ?? null, o)}
            value={opportunity.value}
            note={o.components.every((c) => c.source === null) ? "Needs a Trend Score, a landed margin or a Saturation score." : undefined}
          />
          <Chips explanation={o} />
          {opportunity.value != null && <ScoreExplanation kind="opportunity" explanation={o} />}
        </Card>
        <Numeric kind="saturation" title="Saturation" anchor="saturation" latest={latest.saturation} now={now} />
        <Lifecycle latest={latest.lifecycle} now={now} />
      </div>
    </section>
  );
}

/** A score card: title, Beta, its body, then the row's as of and the score's /methodology anchor (MT-1). Focusable
 *  only by script, so a link to `#score-<kind>` lands on it. */
function Card({ kind, title, beta, anchor, asOf, children }: { kind: string; title: string; beta?: boolean; anchor: string; asOf: React.ReactNode; children: React.ReactNode }) {
  return (
    <article
      id={`score-${kind}`}
      data-score
      tabIndex={-1}
      aria-labelledby={`score-${kind}-title`}
      className={cn("flex min-w-0 scroll-mt-18 flex-col gap-3 px-4 py-3 focus:outline-2 focus:outline-offset-2 focus:outline-ring lg:scroll-mt-4", card)}
    >
      <header className="flex items-center gap-2">
        <h3 id={`score-${kind}-title`} className="text-label text-muted-foreground">
          {title}
        </h3>
        {beta && <BetaPill />}
      </header>
      {children}
      <footer className="mt-auto flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-border-subtle pt-2 text-micro text-subtle-foreground">
        {asOf ?? <span />}
        <Link href={`/methodology#${anchor}`} className={link}>
          How {title} works
        </Link>
      </footer>
    </article>
  );
}

// The amber chips are one click from what fixes or explains them: duty from the landed margin's "Set duty" (imp-368),
// a stale input from the freshness rule and its cadences (imp-589).
const CAUTION: Record<string, { href: string; label: string }> = {
  "Duty not set": { href: "/settings#duty", label: "Duty not set: set it in Settings" },
  "Stale input": { href: "/methodology#confidence", label: "Stale input: how freshness counts" },
};

/** A score's chips (amber cautions, the red margin floor), with a glyph and words, never colour alone. */
function Chips({ explanation }: { explanation: Explanation }) {
  const list = chips(explanation);
  if (list.length === 0) return null;
  return (
    <p className="flex flex-wrap gap-1.5">
      {list.map((text) => {
        const body = (
          <>
            <TriangleAlert className="size-3" aria-hidden />
            {text}
          </>
        );
        const caution = CAUTION[text];
        return caution ? (
          <Link key={text} href={caution.href} aria-label={caution.label} className={cn(chip, "relative hit-area border-warning/40 bg-warning-muted hover:underline")}>
            {body}
          </Link>
        ) : (
          <span key={text} className={cn(chip, "border-negative/40 bg-negative-muted")}>
            {body}
          </span>
        );
      })}
    </p>
  );
}

const NOT_SCORED = "Scores run nightly; none has scored this product yet.";

function Value({ missing, value, detail, note }: { missing: string | null; value?: number | null; detail?: string; note?: string }) {
  if (missing)
    return (
      <div className="flex flex-col gap-1">
        <p className="text-body text-muted-foreground">{missing}</p>
        {note && <p className="text-label text-subtle-foreground">{note}</p>}
      </div>
    );
  return (
    <p className="flex items-baseline gap-1.5">
      <span className="font-mono text-stat-lg font-semibold text-foreground tabular-nums">{value?.toFixed(1)}</span>
      <span className="text-data text-subtle-foreground">/ 100{detail && ` · ${detail}`}</span>
    </p>
  );
}

/** An "as of", amber past 3 nights; its hover says what it dates. */
function AsOf({ at, now, text, hint }: { at: string; now: number; text: string; hint: string }) {
  const stale = now - Date.parse(at) > STALE_MS;
  return (
    <TapTooltip hint={hint} type="button" className={cn("relative hit-area cursor-help rounded-sm text-left", stale && "text-warning")}>
      {stale && <TriangleAlert className="mr-1 inline size-3 align-[-2px]" aria-hidden />}
      {text}
      {stale && " · stale"}
    </TapTooltip>
  );
}

const rowAsOf = (row: Stored, now: number) => (
  // A row's "as of" is its scored day; its hover names the inputs' cutoff and the model version.
  <AsOf at={row.as_of} now={now} text={`As of ${date(row.day)}`} hint={`Scored for ${date(row.day)} (UTC) from data captured before ${formatUtc(row.as_of)}. Model ${row.model_version}.`} />
);

function Numeric({ kind, title, anchor, latest, now }: { kind: ScoreKind; title: string; anchor: string; latest: Latest; now: number }) {
  const row = "day" in latest ? latest : null;
  const missing = unscored(latest);
  return (
    <Card kind={kind} title={title} beta anchor={anchor} asOf={row && rowAsOf(row, now)}>
      <Value missing={missing} value={row?.value} detail={kind === "saturation" && row?.value != null ? crowding(row.value) : undefined} note={row ? undefined : NOT_SCORED} />
      {row && <Chips explanation={row.explanation} />}
      {row && !missing && <ScoreExplanation kind={kind} explanation={row.explanation} />}
    </Card>
  );
}

/** Lifecycle has a stage, not a value: the rule that fired, and tonight's stage while it waits for a second night. */
function Lifecycle({ latest, now }: { latest: Latest; now: number }) {
  const row = "day" in latest ? latest : null;
  return (
    <Card kind="lifecycle" title="Lifecycle" anchor="lifecycle-stage" asOf={row && rowAsOf(row, now)}>
      {row?.stage ? (
        <>
          <p>
            {/* Daily Pulse's and the Screener's LifecyclePill, at the cards' value size. */}
            <StagePill stage={row.stage} className="h-8 gap-1.5 px-2.5 text-body" />
          </p>
          <div className="flex flex-col gap-1 text-data text-muted-foreground">
            {row.explanation.reason && <p>Rule: {row.explanation.reason}</p>}
            {row.explanation.pending && <p>Pending: {row.explanation.pending}, shown once a second night agrees.</p>}
            <MissingInputs explanation={row.explanation} />
          </div>
        </>
      ) : (
        <Value missing={unscored(latest)} note={row ? undefined : NOT_SCORED} />
      )}
    </Card>
  );
}

function ScoresSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 3xl:grid-cols-4">
      <span className="sr-only" role="status">
        Loading the scores…
      </span>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className={cn("flex flex-col gap-3 px-4 py-3", card)}>
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-7 w-20" />
          <Skeleton className="h-1.5 w-full" />
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-4/6" />
          </div>
          <Skeleton className="h-3.5 w-32" />
        </div>
      ))}
    </div>
  );
}
