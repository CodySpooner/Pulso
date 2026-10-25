"use client";

import Link from "next/link";

import { LogoMark } from "@/components/pulso/logo";
import { Button } from "@/components/ui/button";
import { useOncePerSession } from "@/lib/navigation";

const steps = [
  { when: "Phase 1", title: "Collection starts", body: "Competitor Shopify stores, CJ Dropshipping and Google Trends, collected on your PC." },
  { when: "About 7 days later", title: "First movers", body: "Enough daily snapshots to compute 7-day growth and lifecycle stages." },
  { when: "Every morning", title: "Daily Pulse fills in", body: "Emerging products, movers, launches, alerts and your watchlist, from last night's data." },
];

// The first-run card, while no section of the latest day has anything (vault Features/Daily Pulse, Phase 0 state). The
// mark draws once per session, on a client navigation (Motion System pattern 18).
export function FirstRun() {
  const draw = useOncePerSession("pulso:logo-draw");
  return (
    <section aria-labelledby="first-run-title" className="rounded-xl border border-border bg-card p-6 shadow-card">
      <div className="flex flex-col gap-6 md:flex-row md:items-center">
        <div className="relative grid size-16 shrink-0 place-items-center overflow-hidden rounded-xl border border-border bg-background">
          <div
            aria-hidden
            className="absolute inset-0 bg-[linear-gradient(var(--border-subtle)_1px,transparent_1px),linear-gradient(90deg,var(--border-subtle)_1px,transparent_1px)] bg-size-[8px_8px] [mask-image:radial-gradient(circle,black_20%,transparent_75%)]"
          />
          <LogoMark draw={draw} className="relative size-9 text-brand" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h2 id="first-run-title" className="text-title-2 font-semibold text-foreground">
            Your first pulse arrives once collectors run
          </h2>
          <p className="max-w-[64ch] text-body text-muted-foreground">
            Collectors run on your PC. Pulso needs about 7 days of snapshots before movers and lifecycle stages mean
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
  );
}
