"use client";

import { TriangleAlert } from "lucide-react";

import { TapTooltip } from "@/components/data-health/atoms";
import type { components } from "@/lib/api/schema";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A number with its provenance, or null with the reason nothing backs it (the API's `Sourced | NoSource`, DEC-238).
 *  openapi-fetch's response types drop a key typed only `null`, so `value` is optional here: test `"reason" in`. */
export type Stat = components["schemas"]["Sourced"] | { reason: string; value?: null };

/** Where a number came from (vault Features/Methodology & Confidence): source, UTC as-of, the method of an estimate
 *  and the raw payload. `now` is when the data was fetched, so "ago" never ticks (no fake liveness). */
export function ProvenanceCard({ stat, label, now }: { stat: Stat; label: string; now: number }) {
  return (
    <div className="flex flex-col gap-1.5 py-0.5">
      <p className="font-medium text-foreground">{label}</p>
      {"reason" in stat ? (
        <p className="text-muted-foreground">No source yet. {stat.reason}</p>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-muted-foreground">Source</dt>
          <dd>{stat.source_name}</dd>
          <dt className="text-muted-foreground">As of</dt>
          <dd>
            <time dateTime={stat.as_of}>{formatUtc(stat.as_of)}</time> · {formatAgo(stat.as_of, now)}
            {stat.stale && (
              <span className="ml-1 whitespace-nowrap text-warning">
                <TriangleAlert className="mr-0.5 inline size-3 align-[-1px]" aria-hidden />
                Stale
              </span>
            )}
          </dd>
          {stat.method && (
            <>
              <dt className="text-muted-foreground">Method</dt>
              <dd>Estimate · {stat.method}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Raw payload</dt>
          {/* ponytail: the id, selectable; a link once an admin raw-payload view exists (backlog, DEC-238). */}
          <dd className="font-mono select-all">{stat.raw_payload_id === null ? "Not stored" : `#${stat.raw_payload_id}`}</dd>
        </dl>
      )}
    </div>
  );
}

/** A number in tabular numerals that opens its provenance card on hover, keyboard focus and tap (the Data Health
 *  TapTooltip, DEC-232/235). A stat nothing backs reads "No source yet", never 0 (DEC-040); its card says why. The
 *  card can be hovered, so its raw payload id can be selected. */
export function Metric({
  stat,
  label,
  format,
  now,
  side = "bottom",
  className,
}: {
  stat: Stat;
  label: string;
  format: (value: number) => string;
  now: number;
  side?: "top" | "bottom";
  className?: string;
}) {
  const text = "reason" in stat ? "No source yet" : format(stat.value);
  return (
    <TapTooltip
      hint={<ProvenanceCard stat={stat} label={label} now={now} />}
      side={side}
      contentClassName="pointer-events-auto max-w-72 px-3 py-2"
      type="button"
      aria-label={`${label}: ${text}`}
      className={cn(
        "relative hit-area cursor-help rounded-sm text-left tabular-nums decoration-border-strong decoration-dotted underline-offset-4 hover:underline",
        "reason" in stat && "text-muted-foreground",
        className,
      )}
    >
      {text}
    </TapTooltip>
  );
}
