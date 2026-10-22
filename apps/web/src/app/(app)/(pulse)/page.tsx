import type { Metadata } from "next";
import Link from "next/link";

import { PageHeader } from "@/components/pulso/page-header";
import { StatusDot } from "@/components/pulso/status-dot";
import { Button } from "@/components/ui/button";

import { FirstRunMark } from "./first-run-mark";
import { PulseCards } from "./pulse-cards";

export const metadata: Metadata = { title: "Daily Pulse" };

const steps = [
  { when: "Phase 1", title: "Collection starts", body: "Competitor Shopify stores, CJ Dropshipping and Google Trends, collected on your PC." },
  { when: "About 7 days later", title: "First movers", body: "Enough daily snapshots to compute 7-day growth and lifecycle stages." },
  { when: "Phase 4", title: "Daily Pulse fills in", body: "Emerging products, movers, launches, alerts and your watchlist, every morning." },
];

// Phase 0 empty dashboard (vault Features/Daily Pulse): the real layout in its first-run state, with no
// numbers until collectors produce them. A day is the UTC calendar date (DEC-031).
export default function DailyPulsePage() {
  const now = new Date();
  const day = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" }).format(now);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Daily Pulse"
        meta={
          <>
            <time dateTime={now.toISOString().slice(0, 10)}>{day} (UTC)</time>
            <span aria-hidden>·</span>
            <span>As of — nothing collected yet</span>
          </>
        }
        actions={
          <Link
            href="/admin/data-health"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border-subtle px-2 text-label font-medium text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong"
          >
            <StatusDot state="disabled" />
            No collector host yet
          </Link>
        }
      />

      <section aria-labelledby="first-run-title" className="rounded-xl border border-border bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 md:flex-row md:items-center">
          <div className="relative grid size-16 shrink-0 place-items-center overflow-hidden rounded-xl border border-border bg-background">
            <div
              aria-hidden
              className="absolute inset-0 bg-[linear-gradient(var(--border-subtle)_1px,transparent_1px),linear-gradient(90deg,var(--border-subtle)_1px,transparent_1px)] bg-size-[8px_8px] [mask-image:radial-gradient(circle,black_20%,transparent_75%)]"
            />
            <FirstRunMark />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <h2 id="first-run-title" className="text-title-2 font-semibold text-foreground">
              Your first pulse arrives once collectors run
            </h2>
            <p className="max-w-[64ch] text-body text-muted-foreground">
              Collectors start in Phase 1 on your PC. Pulso needs about 7 days of snapshots before movers and lifecycle stages mean
              anything, so this page shows nothing it can&apos;t source.
            </p>
          </div>
          <Button asChild variant="secondary" className="self-start md:self-center">
            <Link href="/admin/data-health">Open Data Health</Link>
          </Button>
        </div>
        <ol className="mt-6 hidden gap-4 border-t border-border-subtle pt-6 sm:grid sm:grid-cols-3">
          {steps.map((step, i) => (
            <li key={step.title} className="flex gap-3">
              <span className="grid size-6 shrink-0 place-items-center rounded-full border border-border font-mono text-micro text-muted-foreground">
                {i + 1}
              </span>
              <div className="flex flex-col gap-0.5">
                <span className="text-label text-subtle-foreground">{step.when}</span>
                <span className="text-data font-medium text-foreground">{step.title}</span>
                <span className="text-data text-muted-foreground">{step.body}</span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <PulseCards />
    </div>
  );
}
