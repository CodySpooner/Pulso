import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { EmptyState } from "@/components/pulso/empty-state";
import { PageHeader } from "@/components/pulso/page-header";
import { Button } from "@/components/ui/button";
import { CURRENT_PHASE, isBuilt, PHASES, resolveRoute } from "@/lib/nav";
import { cn } from "@/lib/utils";

// Every SPEC §10 route that a later phase builds lands here and shows the "no source yet" state
// (vault Design/UI States). A phase that builds a route adds its own folder, which takes precedence.
function routeFor(slug: string[]) {
  const route = resolveRoute(`/${slug.join("/")}`);
  return route && !isBuilt(route.item) ? route : undefined;
}

export async function generateMetadata({ params }: PageProps<"/[...slug]">): Promise<Metadata> {
  return { title: routeFor((await params).slug)?.item.label ?? "Page not found" };
}

export default async function ComingSoonPage({ params }: PageProps<"/[...slug]">) {
  const route = routeFor((await params).slug);
  if (!route) notFound();
  const { item } = route;

  return (
    <div className="mx-auto flex w-full max-w-280 flex-col gap-6">
      <PageHeader title={item.label} description={item.summary} />
      <section aria-label="Status" className="rounded-xl border border-border bg-card shadow-card">
        <EmptyState
          icon={item.icon}
          headingLevel="h2"
          title={`${item.label} arrives in Phase ${item.phase}`}
          action={
            <Button asChild variant="secondary">
              <Link href="/">Back to Daily Pulse</Link>
            </Button>
          }
        >
          Phase {item.phase}, {PHASES[item.phase]}, builds this page. Pulso is in Phase {CURRENT_PHASE}, {PHASES[CURRENT_PHASE]}.
          Nothing here is shown until it comes from a real source.
        </EmptyState>
        <div className="border-t border-border-subtle px-6 py-5">
          <ol aria-label="Build phases" className="flex gap-1">
            {PHASES.map((name, phase) => (
              <li
                key={name}
                className={cn(
                  "h-1 flex-1 rounded-full",
                  phase === CURRENT_PHASE ? "bg-brand" : phase === item.phase ? "bg-muted-foreground" : "bg-border",
                )}
              >
                <span className="sr-only">
                  Phase {phase}, {name}
                  {phase === CURRENT_PHASE && ", in progress"}
                  {phase === item.phase && ", builds this page"}
                </span>
              </li>
            ))}
          </ol>
          <div aria-hidden className="mt-3 flex flex-wrap justify-between gap-2 text-label text-subtle-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-brand" />
              Now: Phase {CURRENT_PHASE} · {PHASES[CURRENT_PHASE]}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-muted-foreground" />
              This page: Phase {item.phase} · {PHASES[item.phase]}
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
