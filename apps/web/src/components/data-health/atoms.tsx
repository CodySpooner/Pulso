import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CirclePause,
  CircleX,
  Clock,
  LoaderCircle,
  ShieldX,
  SkipForward,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { useRef, useState } from "react";

import { CopyButton, SelectableId } from "@/components/pulso/copy-button";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isProblem } from "@/lib/api/client";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { SourceState } from "./model";

// Small Data Health building blocks. Status never relies on colour alone: every pill has an icon and a
// label (vault Features/Data Health, Acceptance criteria).

export type Tone = "neutral" | "muted" | "info" | "warning" | "negative";

const toneClass: Record<Tone, string> = {
  neutral: "border border-border text-muted-foreground",
  muted: "border border-dashed border-border-strong text-subtle-foreground",
  info: "bg-info/12 text-info",
  warning: "bg-warning-muted text-warning",
  negative: "bg-negative-muted text-negative",
};

export function Pill({ tone, icon: Icon, children, className }: { tone: Tone; icon: LucideIcon; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex h-5.5 shrink-0 items-center gap-1 rounded-sm px-1.5 text-label font-medium whitespace-nowrap", toneClass[tone], className)}>
      <Icon className="size-3.5" aria-hidden />
      {children}
    </span>
  );
}

export const sourceStates: Record<SourceState, { label: string; icon: LucideIcon; tone: Tone; hint: string }> = {
  blocked: { label: "Blocked", icon: ShieldX, tone: "negative", hint: "The block rule tripped and the adapter turned itself off (§4.2)." },
  failing: { label: "Failing", icon: CircleX, tone: "negative", hint: "The last run failed." },
  overdue: { label: "Overdue", icon: Clock, tone: "warning", hint: "A scheduled run in the last 24 h was missed and not caught up." },
  skipped: {
    label: "Skipped",
    icon: SkipForward,
    tone: "warning",
    hint: "The latest slot was skipped while an earlier run of the same job was active, so it collected nothing. It counts as missed until a run collects it.",
  },
  partial: { label: "Partial", icon: CircleAlert, tone: "warning", hint: "The last run collected only some targets." },
  running: { label: "Running", icon: LoaderCircle, tone: "info", hint: "A run is queued or running." },
  disabled: { label: "Disabled", icon: CirclePause, tone: "muted", hint: "Disabled by the owner. Nothing is collected." },
  never: { label: "Never run", icon: CircleDashed, tone: "muted", hint: "No run recorded yet." },
  healthy: { label: "Healthy", icon: CircleCheck, tone: "neutral", hint: "The last run succeeded." },
};

/** A source's state with its hint on hover, keyboard focus and tap (imp-073). The hint is click-through, so an
 * open one never covers a control. */
export function StatePill({ state }: { state: SourceState }) {
  const s = sourceStates[state];
  const [open, setOpen] = useState(false);
  const pressedOpen = useRef<boolean | null>(null); // Radix closes on pointerdown, so the click needs the state before it
  return (
    <Tooltip open={open} onOpenChange={setOpen}>
      <TooltipTrigger
        className="relative hit-area inline-flex rounded-sm"
        onPointerDown={() => {
          pressedOpen.current = open;
        }}
        onClick={(e) => {
          e.preventDefault(); // Radix closes on click; a tap, click or Enter toggles instead
          setOpen(!(pressedOpen.current ?? open));
          pressedOpen.current = null;
        }}
      >
        <Pill tone={s.tone} icon={s.icon}>
          {s.label}
        </Pill>
      </TooltipTrigger>
      <TooltipContent className="pointer-events-none">{s.hint}</TooltipContent>
    </Tooltip>
  );
}

const runStatusLabel: Record<string, string> = {
  success: "Succeeded",
  partial: "Partial",
  failed: "Failed",
  blocked: "Blocked",
  queued: "Queued",
  running: "Running",
  skipped: "Skipped",
  pending: "Pending",
};

/** A run or target status in words; unknown values pass through. */
export const runStatus = (status: string) => runStatusLabel[status] ?? status;

/** A value the API doesn't serve yet: "—", never 0 (DEC-040). The reason is on hover and for screen readers. */
export function Missing({ reason = "No source yet", className }: { reason?: string; className?: string }) {
  return (
    <span title={reason} className={cn("text-subtle-foreground", className)}>
      <span aria-hidden>—</span>
      <span className="sr-only">{reason}</span>
    </span>
  );
}

/** Relative time with the UTC time and the source on hover. */
export function Ago({ iso, now, source, className }: { iso: string; now: number; source: string; className?: string }) {
  return (
    <time dateTime={iso} title={`${formatUtc(iso)} · ${source}`} className={cn("whitespace-nowrap", className)}>
      {formatAgo(iso, now)}
    </time>
  );
}

/** A panel's failed request: cause, Retry and the API request id (vault Design/UI States, Error inline).
 *  Its title is an h3 under the panel's h2; one that stands in for the panels directly under the h1 is an h2. */
export function PanelError({
  title,
  error,
  retry,
  headingLevel,
  className,
}: {
  title: string;
  error: unknown;
  retry: () => void;
  headingLevel?: "h2" | "h3";
  className?: string;
}) {
  const problem = isProblem(error) ? error : null;
  return (
    <EmptyState
      icon={TriangleAlert}
      tone="error"
      size="sm"
      title={title}
      headingLevel={headingLevel}
      className={className}
      action={
        <>
          <Button size="sm" variant="primary" onClick={retry}>
            Retry
          </Button>
          {problem && <CopyButton value={problem.request_id} label="Copy error ID" />}
        </>
      }
    >
      {problem ? (
        <p>
          {problem.detail}{" "}
          <span className="font-mono text-label text-subtle-foreground">
            Error ID <SelectableId value={problem.request_id} label="Error ID" />
          </span>
        </p>
      ) : (
        <p>The Pulso API didn&apos;t answer. When it runs on your PC, this also means the PC is off.</p>
      )}
    </EmptyState>
  );
}

/** Card / panel shell shared by the page sections (vault Design/Component Inventory, Card `panel`). */
export function Panel({
  id,
  title,
  note,
  actions,
  children,
  className,
}: {
  id: string;
  title: string;
  note?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section aria-labelledby={`${id}-title`} className={cn("flex min-w-0 flex-col rounded-xl border border-border bg-card shadow-card", className)}>
      <header className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle px-4 py-2.5">
        <h2 id={`${id}-title`} className="text-title-3 font-semibold text-foreground">
          {title}
        </h2>
        {note && <span className="text-label text-subtle-foreground">{note}</span>}
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </header>
      {children}
    </section>
  );
}
