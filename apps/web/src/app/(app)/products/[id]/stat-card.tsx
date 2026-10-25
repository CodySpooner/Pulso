import { TriangleAlert } from "lucide-react";

import type { Stat } from "@/components/pulso/metric";
import { formatAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export const card = "rounded-xl border border-border bg-card shadow-card";

type Sourced = Exclude<Stat, { reason: string }>;

/** The stat with the newest as-of, or undefined when none has a source: what a card's caption names. */
export const newest = (stats: Stat[]) =>
  stats.filter((s): s is Sourced => !("reason" in s)).sort((a, b) => Date.parse(b.as_of) - Date.parse(a.as_of))[0];

/** A stat card: label, value, an optional detail line, the value's source and age, or the reason it has none, and an
 *  optional next action after that reason. Children of a `<dl>`. */
export function StatCard({
  label,
  stat,
  now,
  detail,
  action,
  className,
  children,
}: {
  label: string;
  stat: Stat;
  now: number;
  detail?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 px-4 py-3", card, className)}>
      <dt className="text-label text-muted-foreground">{label}</dt>
      <dd className={cn("text-stat-lg font-semibold text-foreground", "reason" in stat ? "text-body font-normal" : "font-mono")}>{children}</dd>
      {detail && <dd className="text-data text-muted-foreground">{detail}</dd>}
      <dd className={cn("line-clamp-2 text-micro text-subtle-foreground", !("reason" in stat) && stat.stale && "text-warning")}>
        {"reason" in stat ? (
          stat.reason
        ) : (
          <>
            {stat.stale && <TriangleAlert className="mr-1 inline size-3 align-[-2px]" aria-hidden />}
            {stat.source_name} · {formatAgo(stat.as_of, now)}
            {stat.stale && " · stale"}
          </>
        )}
      </dd>
      {action && <dd className="mt-0.5">{action}</dd>}
    </div>
  );
}
