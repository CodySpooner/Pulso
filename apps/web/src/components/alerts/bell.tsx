"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, BellOff, CheckCheck, TriangleAlert } from "lucide-react";
import * as m from "motion/react-m";
import { DropdownMenu } from "radix-ui";

import { Ago } from "@/components/data-health/atoms";
import { DeltaBadge } from "@/components/pulso/delta-badge";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAgo, formatUtc } from "@/lib/format";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { useAlertRules, useAlertWrites, useLatestAlerts, useUnreadCount } from "./api";
import { badge, bellLabel, describeAlert, entityHref, FIRES, groupByDay, lastEvaluation, rulesLine, type Alert } from "./model";

const item = "flex cursor-pointer items-center rounded-md outline-none select-none data-highlighted:bg-accent data-disabled:cursor-default data-disabled:text-subtle-foreground";

/** The unread count as a pill. It scales in once when a refetch raises it (Motion System pattern 17); it never loops. */
export function UnreadBadge({ className, spoken }: { className?: string; spoken?: boolean }) {
  const count = useUnreadCount().data?.count;
  const [seen, setSeen] = useState(count);
  const [pops, setPops] = useState(0);
  if (count !== seen) {
    setSeen(count);
    if (count !== undefined && seen !== undefined && count > seen) setPops(pops + 1);
  }
  const text = count === undefined ? null : badge(count);
  if (!text) return null;
  return (
    <>
      <m.span
        key={pops}
        aria-hidden
        initial={pops ? { scale: 0.6 } : false}
        animate={{ scale: 1 }}
        transition={spring.snappy}
        className={cn("h-4.5 min-w-4.5 items-center justify-center rounded-full px-1 text-micro font-semibold tabular-nums", className)}
      >
        {text}
      </m.span>
      {spoken && <span className="sr-only">, {count} unread</span>}
    </>
  );
}

// The top bar's bell (vault Features/Alerts & Notifications, UX spec): a Radix menu, so arrows move through the rows,
// Escape closes and focus returns to the bell. The writes live here, so a read survives the menu closing.
export function AlertsBell() {
  const count = useUnreadCount().data?.count;
  const writes = useAlertWrites();
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        {/* 4px more beside the theme toggle under touch, so their 44px hit squares don't overlap (A11Y-02). */}
        <Button variant="ghost" size="icon" aria-label={bellLabel(count)} data-testid="alerts-bell" className="pointer-coarse:mr-1">
          <Bell strokeWidth={1.5} aria-hidden />
          <UnreadBadge className="absolute -top-1 -right-1 flex bg-button-brand text-button-brand-foreground ring-2 ring-background" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          collisionPadding={16}
          aria-label="Alerts"
          className="z-50 flex max-h-(--radix-dropdown-menu-content-available-height) w-[min(25rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-popover duration-(--duration-base) data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:duration-(--duration-fast) data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-1"
        >
          <Panel count={count} read={(body) => writes.read.mutate({ body })} />
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function Panel({ count, read }: { count: number | undefined; read: (body: { ids?: number[]; all: boolean }) => void }) {
  const latest = useLatestAlerts();
  const rules = useAlertRules().data?.items;
  const now = latest.dataUpdatedAt;
  const items = latest.data?.items;
  const last = rules && now ? lastEvaluation(rules, now) : null;
  return (
    <>
      <div className="flex h-11 shrink-0 items-center border-b border-border-subtle pr-1 pl-3">
        <DropdownMenu.Label className="text-body font-semibold text-foreground">Alerts</DropdownMenu.Label>
        <DropdownMenu.Item
          disabled={!count}
          onSelect={(e) => {
            e.preventDefault(); // stays open: the dots fade where they are
            read({ all: true });
          }}
          className={cn(item, "ml-auto h-8 gap-1.5 px-2 text-label font-medium text-muted-foreground pointer-coarse:h-(--hit-target)")}
        >
          <CheckCheck className="size-3.5" aria-hidden />
          Mark all read
        </DropdownMenu.Item>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
        {latest.isRefetchError && (
          <p className="flex gap-1.5 px-2 py-1.5 text-label text-muted-foreground">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
            Couldn’t refresh. Showing alerts as of {formatUtc(new Date(now).toISOString())}.
          </p>
        )}
        {items && items.length === 0 && (
          <EmptyState icon={BellOff} size="sm" title="No alerts yet">
            {FIRES} {rules && rulesLine(rules)}
          </EmptyState>
        )}
        {items &&
          groupByDay(items, now).map((group) => (
            <DropdownMenu.Group key={group.label}>
              <DropdownMenu.Label className="px-2 pt-2 pb-1 text-micro font-medium text-subtle-foreground uppercase">{group.label}</DropdownMenu.Label>
              {group.items.map((alert) => (
                <Row key={alert.id} alert={alert} now={now} onOpen={() => !alert.read_at && read({ ids: [alert.id], all: false })} />
              ))}
            </DropdownMenu.Group>
          ))}
        {!items && latest.isError && (
          <div className="flex flex-col items-center gap-2 px-4 py-6 text-center text-data text-muted-foreground">
            <TriangleAlert className="size-5 text-negative" strokeWidth={1.5} aria-hidden />
            <p>
              <span className="font-medium text-foreground">Couldn’t load alerts.</span> The Pulso API didn’t answer; when it runs on your PC, the PC may be off.
            </p>
            <DropdownMenu.Item
              onSelect={(e) => {
                e.preventDefault();
                void latest.refetch();
              }}
              className={cn(item, "h-8 border border-border bg-secondary px-3 text-label font-medium text-foreground")}
            >
              Retry
            </DropdownMenu.Item>
          </div>
        )}
        {!items && !latest.isError && <Loading />}
      </div>
      <div className="flex h-11 shrink-0 items-center gap-2 border-t border-border-subtle pr-1 pl-3 text-label text-subtle-foreground">
        {last?.stale && <TriangleAlert className="size-3.5 shrink-0 text-warning" aria-hidden />}
        {last ? (
          <span className={cn(last.stale && "text-foreground")}>
            Last evaluation{" "}
            <time dateTime={last.iso} title={formatUtc(last.iso)}>
              {formatAgo(last.iso, now)}
            </time>
            {last.stale && " · the collector host may be off"}
          </span>
        ) : (
          rules && now > 0 && "No rule evaluated yet"
        )}
        <DropdownMenu.Item asChild className={cn(item, "ml-auto h-8 px-2 font-medium text-foreground pointer-coarse:h-(--hit-target)")}>
          <Link href="/alerts">View all alerts</Link>
        </DropdownMenu.Item>
      </div>
    </>
  );
}

/** AlertItem `popover` (vault Design/Component Inventory): type icon, sentence, signed change, old → new, time, dot. */
function Row({ alert, now, onOpen }: { alert: Alert; now: number; onOpen: () => void }) {
  const d = describeAlert(alert);
  const href = entityHref(alert);
  const body = (
    <>
      <d.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className={cn("truncate text-data", alert.read_at ? "text-muted-foreground" : "font-medium text-foreground")}>
            {!alert.read_at && <span className="sr-only">Unread: </span>}
            {d.title}
          </span>
          {d.pct !== null && <DeltaBadge value={d.pct} goodDirection="down" unit="%" className="text-label" />}
        </span>
        <span className="truncate text-label text-subtle-foreground tabular-nums" title={d.asOf ? `${d.meta} · as of ${formatUtc(d.asOf)}` : d.meta}>
          {d.change && `${d.change} · `}
          {d.meta}
        </span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1.5 pt-0.5">
        <Ago iso={alert.fired_at} now={now} source={d.meta} className="text-label text-subtle-foreground" />
        <span aria-hidden className={cn("size-2 rounded-full bg-brand transition-opacity duration-(--duration-fast) ease-standard", alert.read_at && "opacity-0")} />
      </span>
    </>
  );
  const row = cn(item, "items-start gap-2.5 px-2 py-2");
  return href ? (
    <DropdownMenu.Item asChild onSelect={onOpen} className={row}>
      <Link href={href}>{body}</Link>
    </DropdownMenu.Item>
  ) : (
    <DropdownMenu.Item onSelect={onOpen} className={row}>
      {body}
    </DropdownMenu.Item>
  );
}

function Loading() {
  return (
    <>
      <span className="sr-only" role="status">
        Loading alerts…
      </span>
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} aria-hidden className="flex gap-2.5 px-2 py-2.5">
          <Skeleton className="size-4" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-44" />
            <Skeleton className="h-3 w-56 max-w-full" />
          </div>
          <Skeleton className="h-3 w-10" />
        </div>
      ))}
    </>
  );
}
