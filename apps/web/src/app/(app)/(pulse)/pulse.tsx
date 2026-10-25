"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { keepPreviousData } from "@tanstack/react-query";
import * as m from "motion/react-m";
import { ChevronLeft, ChevronRight, TriangleAlert } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { PageHeader } from "@/components/pulso/page-header";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api } from "@/lib/api/client";
import { duration } from "@/lib/motion";
import { useOncePerSession } from "@/lib/navigation";

import { CardsSkeleton, PulseCard } from "./cards";
import { FirstRun } from "./first-run";
import { cardOrder, dayParam, isBehind, shiftDay, utcDay } from "./model";

const longDay = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const shortDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
const format = (day: string, as = longDay) => as.format(new Date(day));

/** The day lives in the URL (?date=YYYY-MM-DD); none is the latest scored day. A push, so Back steps back a day. */
const go = (date: string | null) => window.history.pushState(null, "", date ? `?date=${date}` : window.location.pathname);

// WF-6b (vault Features/Daily Pulse, DEC-342): GET /v1/pulse for the day in the URL, one card per section. A past day
// reads only what was captured before its cutoff, so it shows what the data said then. Switching days keeps the old
// day's cards dimmed until the new day arrives (opacity only), then swaps them.
export function DailyPulse() {
  const date = dayParam(useSearchParams().get("date"));
  const query = $api.useQuery("get", "/v1/pulse", { params: { query: date ? { date } : {} } }, { enabled: useApiReady(), placeholderData: keepPreviousData });
  const animate = useOncePerSession("pulso:pulse-stagger");
  const pulse = query.data;
  const now = query.dataUpdatedAt;
  const day = date ?? pulse?.day;
  const loaded = pulse && !query.isPlaceholderData;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Daily Pulse"
        meta={
          day ? (
            <>
              <time dateTime={day}>{format(day)} (UTC day)</time>
              <span aria-hidden>·</span>
              <span>{date ? "as the data stood when the day closed" : "the latest scored day"}</span>
            </>
          ) : (
            <Skeleton className="h-4 w-72 max-w-full" />
          )
        }
        actions={
          <>
            <div role="group" aria-label="Day" className="flex h-(--button-h-md) items-center rounded-md border border-border bg-secondary">
              <Button variant="ghost" size="icon-sm" aria-label="Previous day" disabled={!day} onClick={() => go(shiftDay(day!, -1))}>
                <ChevronLeft aria-hidden />
              </Button>
              <div aria-live="polite" className="min-w-22 px-1 text-center text-data font-medium text-foreground tabular-nums">
                {day ? format(day, shortDay) : <Skeleton className="mx-auto h-3.5 w-12" />}
              </div>
              <Button variant="ghost" size="icon-sm" aria-label="Next day" disabled={!date || !now || date >= utcDay(now)} onClick={() => go(shiftDay(date!, 1))}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
            <Button disabled={!date} onClick={() => go(null)}>
              Latest
            </Button>
          </>
        }
      />
      {query.isRefetchError && <StaleLine boxed what="Couldn’t refresh the Daily Pulse" error={query.error} asOf={now} retry={() => void query.refetch()} />}
      {!pulse ? (
        query.isError ? (
          <section className="rounded-xl border border-border bg-card shadow-card">
            <PanelError headingLevel="h2" size="md" title="Couldn’t load the Daily Pulse" error={query.error} retry={() => void query.refetch()} />
          </section>
        ) : (
          <CardsSkeleton />
        )
      ) : (
        <>
          {loaded && !date && isBehind(pulse.day, now) && (
            <p className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning-muted px-4 py-2.5 text-data text-foreground">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden />
              <span>
                <span className="font-medium">Nothing scored since {format(pulse.day)}.</span> The nightly scoring hasn’t run, so the collector host may be off.{" "}
                <Link href="/admin/data-health" className="rounded-sm font-medium text-foreground underline underline-offset-4">
                  Open Data Health
                </Link>
              </span>
            </p>
          )}
          {loaded && !date && Object.values(pulse.sections).every((s) => s.status !== "ok") && <FirstRun />}
          <m.div
            aria-busy={query.isPlaceholderData}
            animate={{ opacity: query.isPlaceholderData ? 0.5 : 1 }}
            transition={{ duration: duration.fast }}
            className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6 lg:[&>:last-child:nth-child(odd)]:col-span-2"
          >
            {cardOrder(pulse.sections).map((id, i) => (
              <PulseCard key={id} id={id} pulse={pulse} index={i} animate={animate} />
            ))}
          </m.div>
        </>
      )}
    </div>
  );
}
