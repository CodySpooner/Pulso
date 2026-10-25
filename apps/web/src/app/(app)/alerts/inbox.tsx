"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { keepPreviousData } from "@tanstack/react-query";
import { Archive, ArchiveRestore, BellOff, Check, CheckCheck, SearchX, SkipForward, TriangleAlert } from "lucide-react";
import * as m from "motion/react-m";

import { useAlertRules, useAlertWrites, useUnreadCount } from "@/components/alerts/api";
import { UnreadBadge } from "@/components/alerts/bell";
import { describeAlert, entityHref, FIRES, gapSpan, lastEvaluation, rulesLine, TYPES, type Alert } from "@/components/alerts/model";
import { useApiReady } from "@/components/data-health/api";
import { Ago, PanelError, StaleLine } from "@/components/data-health/atoms";
import { LoadMore } from "@/components/data-health/load-more";
import { DeltaBadge } from "@/components/pulso/delta-badge";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { formatAgo, formatUtc } from "@/lib/format";
import { spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

type Write = "read" | "archive" | "unarchive";

const box = "rounded-xl border border-border bg-card shadow-card";
const control =
  "h-(--button-h-md) min-w-0 rounded-md border border-border bg-secondary px-2.5 text-data text-foreground transition-colors duration-(--duration-fast) hover:border-border-strong";
// md and up a dense table; on a phone each row is a card, its cells placed on a three-column grid.
const cell = "border-b border-border-subtle px-3 whitespace-nowrap max-md:border-0 max-md:p-0";
const COLUMNS = ["Alert", "Change", "Source", "Fired"];

// WF-4b (DEC-333): the Inbox and Archived views of the workspace's alerts. The URL holds the view, type and read
// filters; replacing it keeps Back, like Amazon ranks. A selection belongs to the URL it was made on.
export function AlertsInbox() {
  const params = useSearchParams();
  const key = params.toString();
  const archived = params.get("view") === "archived";
  const [type, unread] = [params.get("type"), params.get("unread")];
  const [selection, setSelection] = useState<{ key: string; ids: number[] }>({ key, ids: [] });
  const ids = selection.key === key ? selection.ids : [];
  const select = (next: number[]) => setSelection({ key, ids: next });
  const set = useCallback((next: Record<string, string | null>) => {
    const search = new URLSearchParams(window.location.search);
    for (const [name, value] of Object.entries(next)) {
      if (value === null) search.delete(name);
      else search.set(name, value);
    }
    const text = search.toString();
    window.history.replaceState(null, "", text ? `?${text}` : window.location.pathname);
  }, []);
  const filters = { archived: archived || undefined, type: type ?? undefined, unread: unread === "true" ? true : unread === "false" ? false : undefined };
  const query = $api.useInfiniteQuery(
    "get",
    "/v1/alerts",
    { params: { query: { ...filters, limit: 50 } } },
    { enabled: useApiReady(), pageParamName: "cursor", initialPageParam: null, getNextPageParam: (page) => page.next_cursor, placeholderData: keepPreviousData },
  );
  const rules = useAlertRules().data?.items;
  const count = useUnreadCount().data?.count;
  const writes = useAlertWrites();
  const act = (write: Write, chosen: number[]) => {
    const done = { onSuccess: () => select(ids.filter((id) => !chosen.includes(id))) };
    if (write === "read") writes.read.mutate({ body: { ids: chosen, all: false } }, done);
    else writes[write].mutate({ body: { ids: chosen } }, done);
  };
  const failed = Object.values(writes).find((w) => w.isError);
  const now = query.dataUpdatedAt;
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];
  const last = rules && now ? lastEvaluation(rules, now) : null;
  const tab = (view: string | null) => {
    const search = new URLSearchParams(params);
    if (view) search.set("view", view);
    else search.delete("view");
    return `/alerts${search.size ? `?${search}` : ""}`;
  };

  return (
    <div className="flex flex-col gap-4">
      <nav aria-label="Alert views" className="flex gap-4 border-b border-border-subtle">
        {[
          ["Inbox", null],
          ["Archived", "archived"],
        ].map(([label, view]) => (
          <Link
            key={label}
            href={tab(view)}
            aria-current={archived === (view !== null) ? "page" : undefined}
            className="relative flex h-9 items-center gap-1.5 rounded-sm text-data font-medium text-muted-foreground hover:text-foreground aria-[current=page]:text-foreground"
          >
            {label}
            {view === null && <UnreadBadge spoken className="flex bg-secondary text-muted-foreground" />}
            {archived === (view !== null) && <m.span layoutId="alerts-view" transition={spring.snappy} className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-brand" />}
          </Link>
        ))}
      </nav>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Type" className={control} value={type ?? ""} onChange={(e) => set({ type: e.target.value || null })}>
          <option value="">All types</option>
          {Object.entries(TYPES).map(([value, t]) => (
            <option key={value} value={value}>
              {t.label}
            </option>
          ))}
          {type && !TYPES[type] && <option value={type}>{type}</option>}
        </select>
        <select aria-label="Read state" className={control} value={unread ?? ""} onChange={(e) => set({ unread: e.target.value || null })}>
          <option value="">Read and unread</option>
          <option value="true">Unread</option>
          <option value="false">Read</option>
        </select>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {ids.length > 0 ? (
            <>
              <span className="text-label text-muted-foreground tabular-nums">{ids.length} selected</span>
              {!archived && (
                <Button size="sm" onClick={() => act("read", ids)}>
                  <Check aria-hidden />
                  Mark read
                </Button>
              )}
              <Button size="sm" onClick={() => act(archived ? "unarchive" : "archive", ids)}>
                {archived ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />}
                {archived ? "Unarchive" : "Archive"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => select([])}>
                Clear
              </Button>
            </>
          ) : (
            !archived && (
              <Button size="sm" variant="ghost" disabled={!count} onClick={() => writes.read.mutate({ body: { all: true } })}>
                <CheckCheck aria-hidden />
                Mark all read
              </Button>
            )
          )}
        </div>
      </div>
      {rules && (
        <div className="flex flex-col gap-1 text-label text-subtle-foreground">
          <p>
            {last?.stale && <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-warning" aria-hidden />}
            {rulesLine(rules)}{" "}
            {last ? (
              <span className={cn(last.stale && "text-foreground")}>
                Last evaluation <time dateTime={last.iso} title={formatUtc(last.iso)}>{formatAgo(last.iso, now)}</time>
                {last.stale ? ": over 26 h ago, so the collector host may be off." : "."}
              </span>
            ) : (
              "No rule has been evaluated yet."
            )}
          </p>
          {rules
            .filter((r) => r.status === "skipped")
            .map((r) => (
              <p key={r.id}>
                <SkipForward className="mr-1 inline size-3.5 align-[-2px] text-warning" aria-hidden />
                <span className="text-foreground">{r.name}</span>: 1 evaluation skipped: {gapSpan(r.skipped)}. It fires on the next gap-free reading.
              </p>
            ))}
        </div>
      )}
      {failed && (
        <p role="alert" className="text-label text-foreground">
          <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-negative" aria-hidden />
          <span className="font-medium text-negative">Couldn’t update the alerts.</span>{" "}
          {isProblem(failed.error) ? failed.error.detail : "The Pulso API didn’t answer. When it runs on your PC, this also means the PC is off."}
        </p>
      )}
      {query.isRefetchError && <StaleLine boxed what="Couldn’t refresh alerts" error={query.error} asOf={now} retry={() => void query.refetch()} />}
      {!query.data ? (
        query.isError ? (
          <section className={box}>
            <PanelError headingLevel="h2" size="md" title="Couldn’t load alerts" error={query.error} retry={() => void query.refetch()} />
          </section>
        ) : (
          <Loading />
        )
      ) : rows.length === 0 ? (
        <section className={box}>
          {type || unread ? (
            <EmptyState icon={SearchX} headingLevel="h2" title="No alert matches these filters" action={<Button onClick={() => set({ type: null, unread: null })}>Clear filters</Button>} />
          ) : archived ? (
            <EmptyState icon={Archive} headingLevel="h2" title="Nothing archived">
              Archive an alert from the Inbox to keep it out of the way. It waits here, and Unarchive brings it back.
            </EmptyState>
          ) : (
            <EmptyState icon={BellOff} headingLevel="h2" title="No alerts yet">
              {FIRES} {rules && rulesLine(rules)}
            </EmptyState>
          )}
        </section>
      ) : (
        <>
          <div
            role="region"
            aria-label={archived ? "Archived alerts" : "Alerts inbox"}
            tabIndex={0}
            className={cn(box, "max-h-[max(24rem,calc(100dvh-20rem))] overflow-auto overscroll-contain max-md:max-h-none max-md:overflow-visible max-md:border-0 max-md:bg-transparent max-md:shadow-none")}
          >
            <table className="w-full border-separate border-spacing-0 zone-data max-md:block">
              <thead className="sticky top-0 z-20 bg-card max-md:hidden">
                <tr className="row-h text-label text-muted-foreground">
                  <th scope="col" className={cn(cell, "w-10 border-border bg-card")}>
                    <input
                      type="checkbox"
                      aria-label="Select every loaded alert"
                      className="size-4 accent-brand"
                      checked={ids.length === rows.length}
                      ref={(el) => void (el && (el.indeterminate = ids.length > 0 && ids.length < rows.length))}
                      onChange={(e) => select(e.target.checked ? rows.map((a) => a.id) : [])}
                    />
                  </th>
                  {COLUMNS.map((name) => (
                    <th key={name} scope="col" className={cn(cell, "border-border bg-card font-medium", name === "Fired" ? "num" : "text-left")}>
                      {name}
                    </th>
                  ))}
                  <th scope="col" className={cn(cell, "border-border bg-card")}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="max-md:flex max-md:flex-col max-md:gap-2">
                {rows.map((alert) => (
                  <Row
                    key={alert.id}
                    alert={alert}
                    now={now}
                    archived={archived}
                    checked={ids.includes(alert.id)}
                    onCheck={(on) => select(on ? [...ids, alert.id] : ids.filter((id) => id !== alert.id))}
                    onOpen={() => !alert.read_at && writes.read.mutate({ body: { ids: [alert.id], all: false } })}
                    act={(write) => act(write, [alert.id])}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <LoadMore
            note={`${rows.length} ${archived ? "archived " : ""}${rows.length === 1 ? "alert" : "alerts"}, newest first`}
            label="Load more"
            more={query.hasNextPage}
            pending={query.isFetchingNextPage}
            error={query.isFetchNextPageError ? query.error : null}
            errorTitle="Couldn’t load more alerts"
            onLoad={() => void query.fetchNextPage()}
          />
        </>
      )}
    </div>
  );
}

// AlertItem `page`: rows never animate (Motion System); the unread dot fades in place.
function Row({
  alert,
  now,
  archived,
  checked,
  onCheck,
  onOpen,
  act,
}: {
  alert: Alert;
  now: number;
  archived: boolean;
  checked: boolean;
  onCheck: (on: boolean) => void;
  onOpen: () => void;
  act: (write: Write) => void;
}) {
  const d = describeAlert(alert);
  const href = entityHref(alert);
  const name = `${d.title}, ${formatAgo(alert.fired_at, now)}`;
  return (
    <tr
      data-selected={checked || undefined}
      className="row-h hover:bg-(--table-row-hover) data-selected:bg-(--table-row-selected) max-md:grid max-md:h-auto max-md:grid-cols-[auto_minmax(0,1fr)_auto] max-md:gap-x-3 max-md:gap-y-1 max-md:rounded-lg max-md:border max-md:border-border max-md:bg-card max-md:p-3"
    >
      <td className={cn(cell, "w-10 max-md:row-span-3")}>
        <input type="checkbox" aria-label={`Select ${name}`} className="relative hit-area size-4 accent-brand" checked={checked} onChange={(e) => onCheck(e.target.checked)} />
      </td>
      <th scope="row" className={cn(cell, "max-w-96 text-left font-normal max-md:col-start-2 max-md:row-start-1")}>
        <span className="flex min-w-0 items-center gap-2">
          <span aria-hidden className={cn("size-2 shrink-0 rounded-full bg-brand transition-opacity duration-(--duration-fast) ease-standard", alert.read_at && "opacity-0")} />
          <d.icon className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
          {href ? (
            <Link href={href} onClick={onOpen} className={cn("relative hit-area truncate rounded-sm hover:underline", alert.read_at ? "text-muted-foreground" : "font-medium text-foreground")}>
              {!alert.read_at && <span className="sr-only">Unread: </span>}
              {d.title}
            </Link>
          ) : (
            <span className={cn("truncate", alert.read_at ? "text-muted-foreground" : "font-medium text-foreground")}>
              {!alert.read_at && <span className="sr-only">Unread: </span>}
              {d.title}
            </span>
          )}
        </span>
      </th>
      <td className={cn(cell, "max-md:col-start-2 max-md:row-start-2")} title={d.asOf ? `${d.meta} · as of ${formatUtc(d.asOf)}` : undefined}>
        <span className="flex items-center gap-2 tabular-nums">
          {d.pct !== null && <DeltaBadge value={d.pct} goodDirection="down" unit="%" />}
          <span className="text-muted-foreground">{d.change ?? "—"}</span>
        </span>
      </td>
      <td className={cn(cell, "text-muted-foreground max-md:col-start-2 max-md:row-start-3 max-md:text-label")}>{d.meta}</td>
      <td className={cn(cell, "num text-muted-foreground max-md:col-start-3 max-md:row-start-1 max-md:text-label")}>
        <Ago iso={alert.fired_at} now={now} source={d.meta} />
      </td>
      <td className={cn(cell, "w-20 max-md:col-start-3 max-md:row-start-2 max-md:row-span-2 max-md:self-end")}>
        <span className="flex justify-end gap-1">
          {!archived && !alert.read_at && (
            <Button size="icon-sm" variant="ghost" aria-label={`Mark read: ${name}`} title="Mark read" onClick={() => act("read")}>
              <Check aria-hidden />
            </Button>
          )}
          <Button size="icon-sm" variant="ghost" aria-label={`${archived ? "Unarchive" : "Archive"}: ${name}`} title={archived ? "Unarchive" : "Archive"} onClick={() => act(archived ? "unarchive" : "archive")}>
            {archived ? <ArchiveRestore aria-hidden /> : <Archive aria-hidden />}
          </Button>
        </span>
      </td>
    </tr>
  );
}

export function Loading() {
  return (
    <>
      <span className="sr-only" role="status">
        Loading alerts…
      </span>
      <div aria-hidden className={cn(box, "flex flex-col")}>
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="flex h-(--table-row-h) items-center gap-4 border-b border-border-subtle px-3 last:border-0">
            <Skeleton className="size-4" />
            <Skeleton className="h-3.5 w-56 max-md:w-32" />
            <Skeleton className="h-3.5 w-32 max-md:hidden" />
            <Skeleton className="ml-auto h-3.5 w-12" />
          </div>
        ))}
      </div>
    </>
  );
}
