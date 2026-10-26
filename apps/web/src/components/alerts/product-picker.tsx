"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { DatabaseZap, LoaderCircle, Package, RotateCw, Search, SearchX, Star, TriangleAlert, type LucideIcon } from "lucide-react";

import { Marked } from "@/components/shell/command-palette";
import { useSearch } from "@/components/shell/palette-search";
import type { components } from "@/lib/api/schema";
import { cn } from "@/lib/utils";

import { pickerStatus } from "./model";

const item =
  "flex min-h-9 cursor-pointer items-center gap-2.5 rounded-md px-2 text-data text-muted-foreground outline-none select-none pointer-coarse:min-h-(--hit-target) data-[selected=true]:bg-accent data-[selected=true]:text-foreground data-[disabled=true]:cursor-default data-[disabled=true]:text-subtle-foreground";
const group =
  "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-label [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-subtle-foreground";
const ICONS: Partial<Record<string, LucideIcon>> = { hint: Search, loading: LoaderCircle, empty: SearchX, "no-source": SearchX, "too-long": SearchX, error: TriangleAlert };

function Row({ value, icon: Icon, label, detail, hint, disabled, onSelect, iconClassName }: {
  value: string;
  icon: LucideIcon;
  label: React.ReactNode;
  detail?: React.ReactNode;
  hint?: React.ReactNode;
  disabled?: boolean;
  onSelect?: () => void;
  iconClassName?: string;
}) {
  return (
    <Command.Item value={value} disabled={disabled} onSelect={onSelect} className={item}>
      <Icon className={cn("size-4 shrink-0", iconClassName)} strokeWidth={1.5} aria-hidden />
      {/* On a phone the detail drops under the label, as in the palette. */}
      <span className="flex min-w-0 flex-1 items-center gap-2.5 max-sm:flex-col max-sm:items-start max-sm:gap-0 max-sm:py-1.5">
        <span className="min-w-0 max-w-full shrink truncate">{label}</span>
        {detail && <span className="min-w-0 max-w-full flex-1 basis-0 truncate text-label text-subtle-foreground max-sm:basis-auto">{detail}</span>}
      </span>
      {hint && <span className="ml-auto shrink-0 text-label text-subtle-foreground">{hint}</span>}
    </Command.Item>
  );
}

/** imp-527: the builder's first step from the Rules tab. A product search through the palette's own query (debounced,
 *  its cache shared), or a watchlist, which needs no product. cmdk gives the combobox and listbox semantics. */
export function ProductPicker({
  lists,
  autoFocus,
  onProduct,
  onList,
}: {
  lists: components["schemas"]["Watchlist"][];
  /** Back from the builder's Change; on opening, the dialog focuses the search itself. */
  autoFocus?: boolean;
  onProduct: (product: { id: string; name: string }) => void;
  onList: (id: string) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const term = query.trim();
  const { search, view } = useSearch(term);
  const status = pickerStatus(view, term);
  const products = view.kind === "results" ? view.results.products : [];
  const listed = lists.filter((l) => l.name.toLowerCase().includes(term.toLowerCase()));
  const Icon = ICONS[status.kind];

  return (
    <Command label="Product or watchlist" shouldFilter={false} loop className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="relative text-subtle-foreground">
        {status.busy ? (
          <LoaderCircle data-testid="picker-busy" className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 motion-safe:animate-spin" strokeWidth={1.5} aria-hidden />
        ) : (
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" strokeWidth={1.5} aria-hidden />
        )}
        <Command.Input
          autoFocus={autoFocus}
          value={query}
          onValueChange={setQuery}
          placeholder="Search products by title…"
          className="h-(--button-h-md) w-full rounded-md border border-border bg-secondary pr-2.5 pl-8 text-body text-foreground transition-colors duration-(--duration-fast) placeholder:text-subtle-foreground hover:border-border-strong pointer-coarse:h-(--hit-target) max-md:text-base"
        />
      </div>
      <p role="status" aria-live="polite" className="sr-only">
        {status.kind === "hint" ? "" : status.text}
      </p>
      {/* A fixed height, so the centred dialog doesn't move as results come and go; a phone's sheet gives it the rest. */}
      <Command.List aria-busy={!!status.busy} className="min-h-0 flex-1 scroll-py-1 overflow-y-auto overscroll-contain sm:h-72 sm:flex-none">
        {products.length > 0 && (
          <Command.Group heading="Products" className={group}>
            {products.map((p) => (
              <Row
                key={p.id}
                value={`product:${p.id}`}
                icon={Package}
                label={<Marked text={p.title} term={term} />}
                detail={p.match.text !== p.title && <>Listed as “<Marked text={p.match.text} term={term} />”</>}
                hint={p.category?.split(" > ").at(-1)}
                onSelect={() => onProduct({ id: p.id, name: p.title })}
              />
            ))}
          </Command.Group>
        )}
        {Icon && (
          <Command.Group className={group}>
            <Row value={`status:${status.kind}`} icon={Icon} iconClassName={cn(status.busy && "motion-safe:animate-spin", status.kind === "error" && "text-warning")} label={status.text} detail={status.detail} disabled />
            {status.kind === "error" && <Row value="status:retry" icon={RotateCw} label="Retry search" onSelect={() => void search.refetch()} />}
            {status.kind === "no-source" && <Row value="status:data-health" icon={DatabaseZap} label="Open Data Health" onSelect={() => router.push("/admin/data-health")} />}
          </Command.Group>
        )}
        {listed.length > 0 && (
          <Command.Group heading="Watchlists" className={group}>
            {listed.map((l) => (
              <Row
                key={l.id}
                value={`watchlist:${l.id}`}
                icon={Star}
                label={
                  <>
                    Any product on <Marked text={l.name} term={term} />
                  </>
                }
                detail="Velocity and Saturation rules"
                hint={`${l.item_count} ${l.item_count === 1 ? "product" : "products"}`}
                onSelect={() => onList(l.id)}
              />
            ))}
          </Command.Group>
        )}
      </Command.List>
    </Command>
  );
}
