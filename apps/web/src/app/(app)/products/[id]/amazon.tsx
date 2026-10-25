"use client";

import Link from "next/link";
import { SearchX, TriangleAlert, Trophy, Unplug, type LucideIcon } from "lucide-react";

import { KINDS } from "@/app/(app)/amazon/model";
import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { Skeleton } from "@/components/ui/skeleton";
import { $api } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

const LABEL = "Amazon · manual import"; // as /amazon labels it (vault Methodology & Confidence)
const IMPORT = "/admin/data-health#import";
const DAY = 86_400_000;
const date = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const day = (iso: string) => date.format(new Date(iso));
const link = "link-inline rounded-sm whitespace-nowrap underline decoration-border-strong underline-offset-2 hover:decoration-current";
const cell = "border-b border-border-subtle px-3";

// AMZ-1c (DEC-293): the imported Amazon lists that rank this product, through a GTIN its listings share. One row per
// list at its newest ranked day; a rank only compares within its own list, so the rows stay in list order.
export function AmazonSection({ id }: { id: string }) {
  const query = $api.useQuery("get", "/v1/products/{product_id}/amazon-ranks", { params: { path: { product_id: id } } }, { enabled: useApiReady() });
  const { data, error } = query;
  const retry = () => void query.refetch();
  return (
    <section aria-labelledby="amazon-title" className="flex flex-col gap-3 border-t border-border-subtle p-4">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="amazon-title" className="text-title-3 font-semibold text-foreground">
          Amazon ranks
        </h2>
        {data?.as_of && (
          <span className="text-label text-subtle-foreground">
            <span className="font-medium text-muted-foreground">{LABEL}</span>, as of{" "}
            <time dateTime={data.as_of} title={data.captured_at ? `Imported ${formatUtc(data.captured_at)}` : undefined}>
              {day(data.as_of)}
            </time>
          </span>
        )}
        <Link href="/amazon" className={cn(link, "ml-auto text-label text-muted-foreground hover:text-foreground")}>
          Every Amazon list
        </Link>
      </header>

      {data && query.isError && <StaleLine boxed what="Couldn't refresh Amazon ranks" error={error} asOf={query.dataUpdatedAt} retry={retry} />}
      {!data && query.isError ? (
        <PanelError title="Couldn't load Amazon ranks" error={error} retry={retry} className="rounded-lg border border-border-subtle" />
      ) : !data ? (
        <div className="flex flex-col gap-1.5" aria-busy="true" aria-label="Loading Amazon ranks">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : data.source === null ? (
        <Note icon={Unplug} title="Amazon: no source yet" href="/admin/data-health" action="Open Data Health">
          Pulso&apos;s database doesn&apos;t have the Amazon source yet, so Amazon files can&apos;t be imported. Update Pulso to add it.
        </Note>
      ) : !data.imported ? (
        <Note icon={Trophy} title="No Amazon import yet" href={IMPORT} action="Open CSV import">
          Import Best Sellers or Movers &amp; Shakers ranks from a tool whose terms allow it, or a list made by hand. Never a scrape.
        </Note>
      ) : data.rows.length === 0 ? (
        <Note icon={SearchX} title="Not in an imported Amazon list">
          No imported Amazon row shares a barcode (GTIN) with this product&apos;s listings. Pulso links by barcode only, never by title.
        </Note>
      ) : (
        <>
          {data.stale && data.as_of && (
            <p className="rounded-lg border border-warning/40 bg-warning-muted px-3 py-2 text-data text-foreground">
              <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-warning" aria-hidden />
              <span className="font-medium">
                The newest Amazon ranks here are from {day(data.as_of)}, {Math.floor((query.dataUpdatedAt - Date.parse(data.as_of)) / DAY)} days ago.
              </span>{" "}
              Ranks move daily: import a fresh file.{" "}
              <Link href={IMPORT} className={link}>
                Open CSV import
              </Link>
            </p>
          )}
          <div className="overflow-hidden rounded-lg border border-border-subtle">
            <table className="w-full border-separate border-spacing-0 zone-data">
              <thead>
                <tr className="row-h text-label text-muted-foreground">
                  <th scope="col" className={cn(cell, "text-left font-medium")}>
                    List
                  </th>
                  <th scope="col" className={cn(cell, "num w-16 font-medium")}>
                    Rank
                  </th>
                  <th scope="col" className={cn(cell, "num font-medium whitespace-nowrap")}>
                    Day
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => {
                  const source = `${LABEL} · as of ${day(row.as_of)} · imported ${formatUtc(row.captured_at)} · ASIN ${row.asin}`;
                  return (
                    <tr key={`${row.category}\n${row.rank_kind}`} className="row-h hover:bg-(--table-row-hover) [&:last-child>*]:border-b-0">
                      <th scope="row" className={cn(cell, "py-1.5 text-left font-normal break-words text-foreground")} title={`Listed on Amazon as “${row.title}”`}>
                        {row.category} <span className="text-subtle-foreground">›</span> {KINDS[row.rank_kind]}
                      </th>
                      <td className={cn(cell, "num font-mono font-medium text-foreground")} title={source}>
                        {row.rank.toLocaleString("en-US")}
                      </td>
                      <td className={cn(cell, "num whitespace-nowrap text-muted-foreground")}>
                        <time dateTime={row.as_of} title={`Imported ${formatUtc(row.captured_at)}`}>
                          {day(row.as_of)}
                        </time>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-micro text-subtle-foreground">Each rank is the product&apos;s best in that list on its newest imported day. Lower is better; ranks never compare across lists.</p>
        </>
      )}
    </section>
  );
}

/** A quiet one-box state: icon, what's missing, why, and the next step when there is one. */
function Note({ icon: Icon, title, href, action, children }: { icon: LucideIcon; title: string; href?: string; action?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-dashed border-border px-3 py-2.5">
      <Icon className="mt-0.5 size-4 shrink-0 text-subtle-foreground" aria-hidden />
      <p className="text-data text-muted-foreground">
        <span className="font-medium text-foreground">{title}.</span> {children}{" "}
        {href && (
          <Link href={href} className={link}>
            {action}
          </Link>
        )}
      </p>
    </div>
  );
}
