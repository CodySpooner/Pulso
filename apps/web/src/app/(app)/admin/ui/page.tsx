import type { Metadata } from "next";
import Link from "next/link";
import { Bookmark, DatabaseZap, Download, Plus, Trash2 } from "lucide-react";

import { DeltaBadge } from "@/components/pulso/delta-badge";
import { EmptyState } from "@/components/pulso/empty-state";
import { PageHeader } from "@/components/pulso/page-header";
import { StatusDot } from "@/components/pulso/status-dot";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { ErrorSample, MotionSamples } from "./samples";
import { specimenRows } from "./specimens";

export const metadata: Metadata = { title: "UI gallery" };

const sections = [
  { id: "tokens", title: "Colour tokens" },
  { id: "type", title: "Type scale" },
  { id: "buttons", title: "Buttons" },
  { id: "table", title: "Table density" },
  { id: "states", title: "States" },
  { id: "motion", title: "Motion" },
] as const;

const swatchGroups = [
  {
    label: "Surfaces",
    items: [
      { token: "--background", tile: "bg-background", role: "Content panel" },
      { token: "--sidebar", tile: "bg-sidebar", role: "Sidebar and page" },
      { token: "--card", tile: "bg-card", role: "Cards and tables" },
      { token: "--popover", tile: "bg-popover", role: "Menus and Ctrl+K" },
      { token: "--secondary", tile: "bg-secondary", role: "Secondary controls" },
      { token: "--skeleton", tile: "bg-skeleton", role: "Loading blocks" },
    ],
  },
  {
    label: "Text",
    items: [
      { token: "--foreground", tile: "bg-background text-foreground", role: "Primary text", text: true },
      { token: "--muted-foreground", tile: "bg-background text-muted-foreground", role: "Secondary text", text: true },
      { token: "--subtle-foreground", tile: "bg-background text-subtle-foreground", role: "Captions and hints", text: true },
    ],
  },
  {
    label: "Meaning",
    items: [
      { token: "--brand", tile: "bg-brand", role: "Brand, focus, selection" },
      { token: "--positive", tile: "bg-positive", role: "Good change" },
      { token: "--negative", tile: "bg-negative", role: "Bad change, failure" },
      { token: "--warning", tile: "bg-warning", role: "Stale, needs attention" },
      { token: "--info", tile: "bg-info", role: "Links and info" },
      { token: "--model", tile: "bg-model", role: "AI and model output" },
    ],
  },
  {
    label: "Lines and focus",
    items: [
      { token: "--border-subtle", tile: "border-2 border-border-subtle", role: "Dividers" },
      { token: "--border", tile: "border-2 border-border", role: "Card edges" },
      { token: "--border-strong", tile: "border-2 border-border-strong", role: "Hover edges" },
      { token: "--ring", tile: "outline-2 outline-offset-2 outline-ring", role: "Focus ring" },
    ],
  },
];

const typeScale = [
  { token: "text-display", className: "text-display font-semibold", sample: "Daily Pulse" },
  { token: "text-title-1", className: "text-title-1 font-semibold", sample: "Page title" },
  { token: "text-title-2", className: "text-title-2 font-semibold", sample: "Section title" },
  { token: "text-title-3", className: "text-title-3 font-semibold", sample: "Card title" },
  { token: "text-body", className: "text-body", sample: "Chrome text for headers, dialogs and empty states." },
  { token: "text-data", className: "text-data", sample: "Data text for table cells and dense panels." },
  { token: "text-label", className: "text-label font-medium", sample: "Labels and column headers" },
  { token: "text-micro", className: "text-micro font-medium", sample: "Badges and key caps" },
  { token: "text-stat-xl", className: "text-stat-xl font-semibold tabular-nums", sample: "1,284" },
  { token: "text-stat-lg", className: "text-stat-lg font-semibold tabular-nums", sample: "42.3%" },
  { token: "font-mono", className: "font-mono text-data", sample: "req_7f3a2c90 · 0123456789" },
];

const figures = ["1,111.11", "8,888.88", "4,070.40"];

const buttonVariants = [
  { variant: "primary", label: "Save screen" },
  { variant: "brand", label: "Start test" },
  { variant: "secondary", label: "Export CSV", icon: Download },
  { variant: "outline", label: "Add to board", icon: Plus },
  { variant: "ghost", label: "Cancel" },
  { variant: "destructive", label: "Delete board", icon: Trash2 },
  { variant: "link", label: "How scores work" },
] as const;

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const th = "sticky top-0 z-10 h-8 border-b border-border bg-card px-2 text-label font-medium whitespace-nowrap text-muted-foreground";

function Panel({ id, title, note, children }: { id: string; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-6 rounded-xl border border-border bg-card shadow-card">
      <header className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle px-4 py-3 md:px-6">
        <h2 id={`${id}-title`} className="text-title-3 font-semibold text-foreground">
          {title}
        </h2>
        {note && <span className="text-label text-subtle-foreground">{note}</span>}
      </header>
      <div className="p-4 md:p-6">{children}</div>
    </section>
  );
}

function Caption({ children }: { children: React.ReactNode }) {
  return <span className="text-label text-subtle-foreground">{children}</span>;
}

// WEB-9 (vault Design/Design System): the owner's review surface for the look and the reference agents copy
// patterns from. Every sample uses the real tokens and components. Behind the same allowlist as the app.
export default function UiGalleryPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="UI gallery"
        description="Every design token, type style, control, state and Phase 0 motion in one place. Numbers here are specimens, not data."
      />
      <nav aria-label="Gallery sections">
        <ul className="flex flex-wrap gap-2 pointer-coarse:gap-y-3">
          {sections.map((s) => (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                className="relative hit-area inline-flex h-8 items-center rounded-md border border-border-subtle px-2.5 text-label font-medium text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong hover:text-foreground"
              >
                {s.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <Panel id="tokens" title="Colour tokens" note="Switch the theme to check both">
        <div className="flex flex-col gap-6">
          {swatchGroups.map((group) => (
            <div key={group.label} className="flex flex-col gap-3">
              <h3 className="text-label font-medium text-muted-foreground">{group.label}</h3>
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {group.items.map((s) => (
                  <li key={s.token} className="flex items-center gap-3">
                    <span aria-hidden className={cn("grid size-10 shrink-0 place-items-center rounded-lg border border-border text-title-3 font-semibold", s.tile)}>
                      {"text" in s && "Aa"}
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <code className="text-label text-foreground">{s.token}</code>
                      <Caption>{s.role}</Caption>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Panel>

      <Panel id="type" title="Type scale" note="Geist Sans and Geist Mono">
        <ul className="flex flex-col">
          {typeScale.map((t) => (
            <li key={t.token} className="flex flex-col gap-1 border-b border-border-subtle py-3 first:pt-0 sm:flex-row sm:items-baseline sm:gap-6">
              <code className="w-28 shrink-0 text-label text-subtle-foreground">{t.token}</code>
              <span className={cn("min-w-0 text-foreground", t.className)}>{t.sample}</span>
            </li>
          ))}
        </ul>
        <div className="mt-6 grid max-w-80 grid-cols-2 gap-6 text-data text-foreground">
          {(["proportional-nums", "tabular-nums"] as const).map((variant) => (
            <div key={variant} className="flex flex-col gap-1">
              <code className="text-label text-subtle-foreground">{variant}</code>
              <div className={cn("flex flex-col items-end", variant)}>
                {figures.map((n) => (
                  <span key={n}>{n}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel id="buttons" title="Buttons" note="Neutral primary; at most one brand button per screen">
        <div className="flex flex-col gap-6">
          <ul className="flex flex-wrap gap-x-6 gap-y-4">
            {buttonVariants.map(({ variant, label, ...rest }) => {
              const Icon = "icon" in rest ? rest.icon : null;
              return (
                <li key={variant} className="flex flex-col items-start gap-2">
                  <Button variant={variant}>
                    {Icon && <Icon aria-hidden />}
                    {label}
                  </Button>
                  <code className="text-label text-subtle-foreground">{variant}</code>
                </li>
              );
            })}
          </ul>
          <ul className="flex flex-wrap items-end gap-x-6 gap-y-4">
            {(["sm", "md", "lg"] as const).map((size) => (
              <li key={size} className="flex flex-col items-start gap-2">
                <Button size={size}>Export CSV</Button>
                <code className="text-label text-subtle-foreground">{size}</code>
              </li>
            ))}
            <li className="flex flex-col items-start gap-2">
              <Button size="icon" variant="ghost" aria-label="Add to board">
                <Bookmark aria-hidden />
              </Button>
              <code className="text-label text-subtle-foreground">icon</code>
            </li>
            <li className="flex flex-col items-start gap-2">
              <Button disabled>Export CSV</Button>
              <code className="text-label text-subtle-foreground">disabled</code>
            </li>
          </ul>
          <Caption>Press Tab to see the focus ring on every control.</Caption>
        </div>
      </Panel>

      <Panel id="table" title="Table density" note="Compact 28 px rows · sticky header · rows never animate">
        <div className="flex flex-col gap-3">
          <Caption>{specimenRows.length} specimen rows, not data. Real cells name their source and as-of time on hover.</Caption>
          {/* `relative` makes the scroller clip the sr-only (absolute) cell text, which otherwise widens the page. */}
          <div role="region" aria-label="Specimen table" tabIndex={0} className="relative max-h-60 overflow-auto rounded-lg border border-border">
            <table className="zone-data w-full min-w-160">
              <thead>
                <tr>
                  <th scope="col" className={cn(th, "text-left")}>
                    Product
                  </th>
                  {["Price", "Margin", "Velocity 7d", "Saturation 7d", "Last seen"].map((label) => (
                    <th key={label} scope="col" className={cn(th, "text-right")}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody title="Specimen value: real cells name their source and as-of time here">
                {specimenRows.map((row) => {
                  const dim = row.stale && "text-muted-foreground";
                  return (
                    <tr key={row.name} className="row-h-compact border-b border-border-subtle last:border-0 hover:bg-(--table-row-hover)">
                      <td className="max-w-56 truncate px-2 font-medium text-foreground">{row.name}</td>
                      <td className={cn("num px-2 text-foreground", dim)}>{money.format(row.priceMinor / 100)}</td>
                      <td className={cn("num px-2 text-foreground", dim)}>
                        {row.margin === null ? (
                          <span title="No source yet" className="text-subtle-foreground">
                            <span aria-hidden>—</span>
                            <span className="sr-only">No source yet</span>
                          </span>
                        ) : (
                          `${row.margin.toFixed(1)}%`
                        )}
                      </td>
                      <td className="num px-2">
                        <DeltaBadge value={row.velocity} unit="%" className={cn(dim)} />
                      </td>
                      <td className="num px-2">
                        <DeltaBadge value={row.saturation} unit="%" goodDirection="down" className={cn(dim)} />
                      </td>
                      <td className="num px-2 whitespace-nowrap text-muted-foreground">
                        <span className="inline-flex items-center gap-1.5">
                          {row.stale && <StatusDot state="warning" />}
                          {row.lastSeen}
                          {row.stale && <span className="sr-only">, stale</span>}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Caption>
            Deltas carry a sign and ▲/▼; colour says whether the change is good (velocity up, saturation down). A stale row dims its
            numbers and shows an amber dot. A missing value is —, never 0.
          </Caption>
        </div>
      </Panel>

      <Panel id="states" title="States" note="Designed for every data view (vault UI States)">
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <StateSample label="Loading: skeleton after 150 ms">
            <div className="flex w-full flex-col gap-3 p-4">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-2/3" />
            </div>
          </StateSample>
          <StateSample label="Empty: first run">
            <EmptyState
              size="sm"
              icon={Bookmark}
              title="No products on this board"
              action={
                <Button asChild size="sm">
                  <Link href="/discover">Go to Discover</Link>
                </Button>
              }
            >
              Save products from Discover or a product page to collect them here.
            </EmptyState>
          </StateSample>
          <StateSample label="Error: inline, the rest of the page keeps working">
            <ErrorSample />
          </StateSample>
          <StateSample label="Stale: older than 1.5× the source interval">
            <div className="flex w-full flex-col">
              <div className="flex h-10 items-center gap-2 border-b border-border-subtle px-4">
                <span className="text-data font-medium text-foreground">Biggest movers</span>
                <span className="ml-auto inline-flex items-center gap-1.5 text-label text-warning">
                  <StatusDot state="warning" />
                  As of 26h ago
                </span>
              </div>
              <p className="p-4 text-data text-muted-foreground">
                The numbers stay. The dot and the time turn amber, and a page banner appears once a core source is 3× late.
              </p>
            </div>
          </StateSample>
          <StateSample label="No source yet">
            <EmptyState size="sm" icon={DatabaseZap} title="Ad data arrives in Phase 8">
              Meta Ad Library and TikTok sources come later. Every source also takes a CSV import.
            </EmptyState>
          </StateSample>
        </ul>
      </Panel>

      <Panel id="motion" title="Motion" note="Transform and opacity only · duration tokens · reduced motion respected">
        <MotionSamples />
      </Panel>
    </div>
  );
}

function StateSample({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex flex-col gap-2">
      <Caption>{label}</Caption>
      <div className="flex flex-1 items-center justify-center rounded-lg border border-border-subtle bg-background">{children}</div>
    </li>
  );
}
