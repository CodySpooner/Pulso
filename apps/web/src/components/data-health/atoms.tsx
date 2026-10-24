import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleHelp,
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
import { OFFLINE_HINT } from "@/components/shell/offline-banner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isProblem } from "@/lib/api/client";
import { formatAgo, formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { SourceState } from "./model";
import { RetryScope, useRetry, useRetryScope } from "./retry";

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
  unknown: {
    label: "Unknown",
    icon: CircleHelp,
    tone: "muted",
    hint: "Missed runs come from the collector host's gap check, which didn't load, so this source may be overdue. Retry on the Collector host card.",
  },
};

/** A hint on hover, keyboard focus and tap (imp-073); the other props go to its trigger. A press opens or keeps
 * the hint, never closes it (imp-173). The hint is click-through, so an open one never covers a control. Without
 * a hint it is inert, so a control whose reason comes and goes (offline, imp-134) stays the same element and keeps
 * focus. `side` defaults to Radix's top. */
export function TapTooltip({
  hint,
  side,
  ...trigger
}: React.ComponentProps<typeof TooltipTrigger> & { hint: React.ReactNode; side?: React.ComponentProps<typeof TooltipContent>["side"] }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const onTrigger = (e: Event | undefined) => !!e && e.target instanceof Node && !!triggerRef.current?.contains(e.target);
  return (
    <Tooltip
      open={open && !!hint}
      onOpenChange={(next) => {
        // Radix closes on any scroll of the trigger's ancestors, including the one focusing an off-screen trigger
        // causes, so a reason shown on focus stays while its trigger keeps focus (imp-156, DEC-213).
        if (!next && window.event?.type === "scroll" && document.activeElement === triggerRef.current) return;
        if (!next && window.event?.type === "pointerdown" && onTrigger(window.event)) return; // Radix closes on a press too (DEC-232)
        setOpen(next && !!hint);
      }}
    >
      <TooltipTrigger
        {...trigger}
        ref={triggerRef}
        onClick={(e) => {
          if (!hint) return; // the click is the control's own
          e.preventDefault(); // Radix closes on click; a tap, click or Enter opens or keeps the reason instead
          // Radix's own opens send this event, which closes any other open tooltip; a press-open does too (imp-155).
          if (!open) document.dispatchEvent(new CustomEvent("tooltip.open"));
          setOpen(true);
        }}
      />
      {/* Hidden while its trigger is scrolled out of view, so a reason kept open never floats over the top bar. A
          press on the trigger is outside the hint, which Radix would take as a dismissing press. */}
      <TooltipContent side={side} hideWhenDetached className="pointer-events-none" onPointerDownOutside={(e) => onTrigger(e) && e.preventDefault()}>
        {hint}
      </TooltipContent>
    </Tooltip>
  );
}

/** A source's state with its hint on hover, keyboard focus and tap. */
export function StatePill({ state }: { state: SourceState }) {
  const s = sourceStates[state];
  return (
    <TapTooltip hint={s.hint} className="relative hit-area inline-flex rounded-sm">
      <Pill tone={s.tone} icon={s.icon}>
        {s.label}
      </Pill>
    </TapTooltip>
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
 *  Its title is an h3 under the panel's h2; one that stands in for the panels directly under the h1 is an h2,
 *  set `size="md"` so it reads like the panel titles it replaces. */
export function PanelError({
  title,
  error,
  retry,
  headingLevel,
  size = "sm",
  className,
}: {
  title: string;
  error: unknown;
  retry: () => void;
  headingLevel?: "h2" | "h3";
  size?: "sm" | "md";
  className?: string;
}) {
  const problem = isProblem(error) ? error : null;
  const { button, failed, online, press } = useRetry(retry);
  return (
    <EmptyState
      icon={TriangleAlert}
      tone="error"
      size={size}
      title={title}
      headingLevel={headingLevel}
      className={className}
      action={
        <>
          {/* Below: above, it would cover the Error ID line over Retry (imp-175). */}
          <TapTooltip hint={online ? null : OFFLINE_HINT} side="bottom" asChild>
            <Button
              ref={button}
              size="sm"
              variant="primary"
              // Locked offline with secondary tokens, not opacity, so its focus ring keeps 3:1 (DEC-185, DEC-206).
              className="aria-disabled:pointer-events-auto aria-disabled:cursor-not-allowed aria-disabled:border-border aria-disabled:bg-secondary aria-disabled:text-subtle-foreground aria-disabled:opacity-100"
              aria-disabled={!online}
              onClick={press}
            >
              Retry
            </Button>
          </TapTooltip>
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
        <p>{API_DOWN}</p>
      )}
      {/* Only a Retry the owner pressed that failed is spoken, once (imp-135); its Retry has taken the lost focus. */}
      <p role="alert" className="sr-only">
        {failed ? `${title}. ${problem ? problem.detail : API_DOWN}` : ""}
      </p>
    </EmptyState>
  );
}

const API_DOWN = "The Pulso API didn't answer. When it runs on your PC, this also means the PC is off.";

/** What a panel lacks while another panel's call has failed (imp-139): one muted line, never a second error. That
 *  panel keeps the error, Retry and error ID, and its Retry restores this too. Not a live region: refetches stay
 *  silent. Set like the Open gaps line that waits on the host card (imp-158). */
export function WaitsLine({ lead, children, className }: { lead: string; children: React.ReactNode; className?: string }) {
  return (
    <p className={cn("text-data text-muted-foreground", className)}>
      <CircleHelp aria-hidden className="mr-1.5 inline size-3.5 align-[-2px] text-subtle-foreground" />
      <span className="font-medium text-foreground">{lead}</span> {children}
    </p>
  );
}

/** A refetch failed while the last data stays on screen (imp-132): what failed, why, how old the data is, Retry
 *  and Copy error ID, in the import panel's error-line layout. A strip under a panel header, or `boxed` inside
 *  padded content. Overlays stack on real data and never replace it (vault Design/UI States). */
export function StaleLine({
  what,
  error,
  asOf,
  retry,
  boxed,
  className,
}: {
  what: string;
  error: unknown;
  asOf: number;
  retry: () => void;
  boxed?: boolean;
  className?: string;
}) {
  const problem = isProblem(error) ? error : null;
  const iso = new Date(asOf).toISOString();
  const { button, failed, online, press } = useRetry(retry);
  return (
    <div
      role="group"
      aria-label={what}
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-2 bg-warning-muted px-4 py-2.5 text-data",
        boxed ? "rounded-lg border border-warning/40" : "border-b border-warning/30",
        className,
      )}
    >
      {/* What, then how old the shown data is (UI States' offline copy), then why. The icon sits in the text, so
          it stays on the first line when the line wraps on a phone. */}
      <p className="min-w-0 flex-[1_1_12rem] text-foreground">
        <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
        <span className="font-medium">{what}.</span> Showing data as of{" "}
        <time dateTime={iso} className="whitespace-nowrap">
          {formatUtc(iso)}
        </time>
        . {problem ? problem.detail : API_DOWN}
      </p>
      {problem && (
        <p className="font-mono text-label text-muted-foreground">
          Error ID <SelectableId value={problem.request_id} label="Error ID" className="inline-block max-w-full break-all" />
        </p>
      )}
      <div className="ml-auto flex gap-2">
        {/* Below, clear of the Error ID line that wraps above Retry on a phone (imp-175). */}
        <TapTooltip hint={online ? null : OFFLINE_HINT} side="bottom" asChild>
          <Button
            ref={button}
            size="sm"
            variant="secondary"
            // Locked offline, dimmed with a token, not opacity, so its focus ring keeps 3:1 (DEC-185, DEC-206).
            className="aria-disabled:pointer-events-auto aria-disabled:cursor-not-allowed aria-disabled:text-subtle-foreground aria-disabled:opacity-100"
            aria-disabled={!online}
            onClick={press}
          >
            Retry
          </Button>
        </TapTooltip>
        {problem && <CopyButton value={problem.request_id} label="Copy error ID" />}
      </div>
      {/* A pressed Retry that failed again, once (imp-135); the line stays, so its Retry keeps focus. */}
      <p role="alert" className="sr-only">
        {failed ? `${what}. ${problem ? problem.detail : API_DOWN}` : ""}
      </p>
    </div>
  );
}

/** Card / panel shell shared by the page sections (vault Design/Component Inventory, Card `panel`). A Retry
 *  inside it that restores the panel leaves focus on its heading (imp-135). */
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
  const heading = useRef<HTMLHeadingElement>(null);
  const retry = useRetryScope(heading);
  return (
    <section aria-labelledby={`${id}-title`} className={cn("flex min-w-0 flex-col rounded-xl border border-border bg-card shadow-card", className)}>
      <header className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle px-4 py-2.5">
        {/* The scroll margin clears the phone's top bar when a restored panel's heading takes focus. */}
        <h2 ref={heading} id={`${id}-title`} tabIndex={-1} className="scroll-mt-18 rounded-sm text-title-3 font-semibold text-foreground lg:scroll-mt-4">
          {title}
        </h2>
        {note && <span className="text-label text-subtle-foreground">{note}</span>}
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </header>
      <RetryScope value={retry}>{children}</RetryScope>
    </section>
  );
}
