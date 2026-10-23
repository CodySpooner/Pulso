"use client";

import { cn } from "@/lib/utils";

import { useHost, useSources } from "./api";
import { attentionCount } from "./model";

// DH-3: blocked, failing and overdue sources put a red count on the Data Health nav item (red only for
// failures, vault Design/App Shell & Navigation). Nothing renders while either call loads, when sources fail
// or at zero. When only the host call failed, the count is a floor and reads "1+" (imp-133).
export function DataHealthNavBadge({ expandedClass, railClass }: { expandedClass?: string; railClass?: string }) {
  const sources = useSources();
  const host = useHost();
  if (!sources.data || host.isPending) return null;
  const { count, atLeast } = attentionCount(sources.data, host.data?.latest_gap_ends, sources.dataUpdatedAt);
  if (count === 0) return null;
  return (
    <>
      <span
        aria-hidden
        data-testid="data-health-badge"
        className={cn("relative ml-auto h-4.5 min-w-4.5 items-center justify-center rounded-full bg-negative-muted px-1 text-micro font-medium text-negative tabular-nums", expandedClass)}
      >
        {count}
        {atLeast && "+"}
      </span>
      {railClass !== undefined && <span aria-hidden className={cn("absolute top-1 left-1/2 ml-1.5 size-2 rounded-full bg-negative ring-2 ring-sidebar", railClass)} />}
      <span className="sr-only">
        , {atLeast && "at least "}
        {count} {count === 1 ? "source needs" : "sources need"} attention
      </span>
    </>
  );
}
