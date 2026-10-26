"use client";

import { TapTooltip } from "@/components/data-health/atoms";
import { formatDelta, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { certainty, missingInputs, penaltySteps, sourceLabel, topReasons, type Explanation, type ScoreKind } from "./score-model";

/** BetaBadge (vault Design/Component Inventory): a heuristic v0 score, until a forecast model is promoted. */
export function BetaPill() {
  return (
    <span title="Heuristic v0 score. Forecast probabilities replace it once enough history exists." className="inline-flex h-5 items-center rounded-sm border border-border px-1.5 text-micro font-medium text-muted-foreground">
      Beta
    </span>
  );
}

const TONE = { positive: "text-positive", negative: "text-negative", neutral: "text-muted-foreground" };
const BAR = { positive: "bg-positive", negative: "bg-negative", neutral: "bg-border-strong" };
const eyebrow = "text-micro font-medium text-subtle-foreground";

/** A score's why (imp-460): its confidence (or coverage until freshness is built), the top 3 reasons in points with
 *  ▲/▼ and a ContributionBar (HTML, vault Design/Charts & Data Viz), each penalty as its own step, and what is missing.
 *  Higher Saturation is worse, so its rising inputs read negative. */
export function ScoreExplanation({ kind, explanation }: { kind: ScoreKind; explanation: Explanation }) {
  const good = kind === "saturation" ? "down" : "up";
  const sure = certainty(explanation);
  const reasons = topReasons(explanation, kind);
  const steps = penaltySteps(explanation);
  const widest = Math.max(...reasons.map((r) => Math.abs(r.points)), ...steps.map((s) => Math.abs(s.points ?? 0)), 1e-9);
  return (
    <div className="flex flex-col gap-3">
      <p className="flex items-center gap-2 text-label">
        <span className="text-muted-foreground">{sure.label}</span>
        <span aria-hidden className="h-1.5 min-w-12 flex-1 overflow-hidden rounded-full bg-secondary">
          <span className="block h-full rounded-full bg-muted-foreground" style={{ width: `${sure.value * 100}%` }} />
        </span>
        <span className="font-mono text-foreground tabular-nums">{Math.round(sure.value * 100)}%</span>
        <span className="text-subtle-foreground">{sure.grade}</span>
      </p>
      {reasons.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className={eyebrow}>Top reasons</p>
          <ul className="flex flex-col">
            {reasons.map((r) => (
              <Step key={r.name} label={r.label} points={r.points} good={good} widest={widest} hint={<Provenance source={r.source} asOf={r.asOf} gap={r.gap} />} />
            ))}
          </ul>
        </div>
      )}
      {steps.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-dashed border-border pt-2">
          <p className={eyebrow}>Penalty</p>
          <ul className="flex flex-col">
            {steps.map((s) => (
              <Step key={s.name} label={s.label} points={s.points} missing={s.missing} good={good} widest={widest} hint={s.source && <Provenance source={s.source} asOf={null} gap={false} />} />
            ))}
          </ul>
        </div>
      )}
      {missingInputs(explanation).map(({ word, labels }) => (
        <p key={word} className="text-label text-subtle-foreground">
          {word}: {labels.join(", ")}
        </p>
      ))}
    </div>
  );
}

/** One waterfall step: glyph, input (its source on hover, focus or tap), bar and signed points; never colour alone. */
function Step({ label, points, missing, good, widest, hint }: { label: string; points: number | null; missing?: string | null; good: "up" | "down"; widest: number; hint: React.ReactNode }) {
  const delta = formatDelta(points, good, 1);
  return (
    <li className="grid min-h-7 grid-cols-[0.75rem_minmax(0,1fr)_minmax(1.5rem,3rem)_3.25rem] items-center gap-x-2 text-data">
      <span aria-hidden className={cn("text-micro", TONE[delta.tone])}>
        {delta.glyph}
      </span>
      {hint ? (
        <TapTooltip
          hint={hint}
          type="button"
          className="relative hit-area cursor-help truncate rounded-sm text-left text-foreground decoration-border-strong decoration-dotted underline-offset-4 hover:underline"
        >
          {label}
        </TapTooltip>
      ) : (
        <span className="truncate text-foreground">{label}</span>
      )}
      {missing ? (
        <span className="col-span-2 justify-self-end text-label text-muted-foreground">{missing}</span>
      ) : (
        <>
          <span aria-hidden className="h-1.5 justify-self-stretch">
            <span className={cn("ml-auto block h-full rounded-full", BAR[delta.tone])} style={{ width: `${(Math.abs(points ?? 0) / widest) * 100}%` }} />
          </span>
          <span className={cn("text-right font-mono tabular-nums", TONE[delta.tone])}>
            {delta.text}
            <span className="sr-only"> points</span>
          </span>
        </>
      )}
    </li>
  );
}

function Provenance({ source, asOf, gap }: { source: string; asOf: string | null; gap: boolean }) {
  return (
    <span className="flex flex-col gap-0.5">
      <span>Source: {sourceLabel(source)}</span>
      {asOf && <span>As of {formatUtc(asOf)}</span>}
      {gap && <span className="text-warning">Its window overlaps a collection gap</span>}
    </span>
  );
}
