"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState, type RefObject } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { Command, defaultFilter } from "cmdk";
import { AnimatePresence, LayoutGroup } from "motion/react";
import * as m from "motion/react-m";
import { Dialog } from "radix-ui";
import { useClerk } from "@clerk/nextjs";
import {
  CornerDownLeft,
  DatabaseZap,
  Factory,
  LoaderCircle,
  LogOut,
  Monitor,
  Moon,
  Package,
  PanelLeft,
  RotateCw,
  Search,
  SearchX,
  Store,
  Sun,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useTheme } from "next-themes";

import { useApiReady } from "@/components/data-health/api";
import { Kbd } from "@/components/ui/kbd";
import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { authBypass } from "@/lib/auth";
import { formatAgo, formatUtc } from "@/lib/format";
import { duration, ease, spring } from "@/lib/motion";
import { allNavItems, isBuilt } from "@/lib/nav";
import { cn } from "@/lib/utils";

import { useShell } from "./app-shell";
import { announce, DEBOUNCE_MS, MIN_QUERY, SEARCH_SCORE, SEARCH_VALUE, searchView, useDebounced, type SearchView } from "./palette-search";

interface Run {
  close: () => void;
}

const item =
  "relative flex h-10 cursor-pointer items-center gap-3 rounded-lg px-2 pointer-coarse:h-11 text-body text-muted-foreground outline-none select-none data-[selected=true]:text-foreground data-[disabled=true]:cursor-default data-[disabled=true]:text-subtle-foreground";
const group =
  "px-1.5 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-label [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-subtle-foreground";

function Row({
  value,
  selected,
  icon: Icon,
  label,
  detail,
  hint,
  keywords,
  disabled,
  onSelect,
  iconClassName,
}: {
  value: string;
  selected: string;
  icon: LucideIcon;
  label: React.ReactNode;
  /** Muted text after the label, truncated first. */
  detail?: React.ReactNode;
  hint?: React.ReactNode;
  iconClassName?: string;
  keywords?: string[];
  disabled?: boolean;
  onSelect?: () => void;
}) {
  return (
    <Command.Item value={value} keywords={keywords} disabled={disabled} onSelect={onSelect} className={item}>
      {selected === value && (
        // The highlight is one shared element that slides between rows (pattern 8), snaps under reduced motion.
        <m.span layoutId="palette-highlight" transition={spring.snappy} className="absolute inset-0 rounded-lg bg-accent" />
      )}
      <Icon className={cn("relative size-4 shrink-0", iconClassName)} strokeWidth={1.5} aria-hidden />
      <span className="relative min-w-0 shrink truncate">{label}</span>
      {detail && <span className="relative min-w-0 flex-1 basis-0 truncate text-label text-subtle-foreground">{detail}</span>}
      {hint && <span className="relative ml-auto shrink-0 text-label text-subtle-foreground">{hint}</span>}
    </Command.Item>
  );
}

function SignOutRow({ selected, run }: { selected: string; run: Run }) {
  const { signOut } = useClerk();
  return (
    <Row
      value="sign-out"
      selected={selected}
      icon={LogOut}
      label="Sign out"
      onSelect={() => {
        run.close();
        void signOut({ redirectUrl: "/sign-in" });
      }}
    />
  );
}

type Hits = components["schemas"];
const PLATFORMS: Record<string, string> = { cj: "CJ Dropshipping" };

// Every search row gets the same tiny score: it shows for any query, keeps the API's order inside its group, and its
// group sorts under the commands that match (cmdk orders groups by their best score, ties in mount order).
const paletteFilter = (value: string, search: string, keywords?: string[]) =>
  value.startsWith(SEARCH_VALUE) ? SEARCH_SCORE : defaultFilter(value, search, keywords);

/** `text` with the first case-insensitive occurrence of `term` emphasised (a fuzzy match has none). */
function Marked({ text, term }: { text: string; term: string }) {
  const at = text.toLowerCase().indexOf(term.toLowerCase());
  if (at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <mark className="bg-transparent font-medium text-foreground">{text.slice(at, at + term.length)}</mark>
      {text.slice(at + term.length)}
    </>
  );
}

/** A store's freshness: when it was last crawled, with a glyph and the word when that's past twice the crawl interval. */
function Crawled({ store, asOf }: { store: Hits["StoreHit"]; asOf: number }) {
  if (!store.last_crawled_at) return "Not crawled yet";
  const ago = formatAgo(store.last_crawled_at, asOf);
  return (
    <span title={`Last crawled ${formatUtc(store.last_crawled_at)}`} className={cn("inline-flex items-center gap-1", store.stale && "text-warning")}>
      {store.stale && <TriangleAlert className="size-3.5" aria-hidden />}
      {store.stale ? `Stale: crawled ${ago}` : `Crawled ${ago}`}
    </span>
  );
}

const TOP = <span className="sr-only">(opens its top product)</span>;

/** A store's or supplier's rows. cmdk sorts only enabled rows and appends them after disabled ones, so the rows with
 *  nowhere to go sit in a second group just below, which takes the heading only when it is alone. */
function VendorGroups<T extends { id: number; top_product_id: string | null }>({
  heading,
  hits,
  row,
}: {
  heading: string;
  hits: T[];
  row: (hit: T) => React.ReactNode;
}) {
  const open = hits.filter((hit) => hit.top_product_id);
  return (
    <>
      <Command.Group heading={heading} className={group}>
        {open.map(row)}
      </Command.Group>
      <Command.Group heading={open.length ? undefined : heading} className={group}>
        {hits.filter((hit) => !hit.top_product_id).map(row)}
      </Command.Group>
    </>
  );
}

// Global search (UX-9, DEC-252): products, stores and suppliers, then one status group. All of them mount together, so
// cmdk keeps them in this order. A store or supplier opens its top product until Store Spy builds their pages.
function SearchGroups({
  view,
  term,
  selected,
  asOf,
  go,
  retry,
}: {
  view: SearchView;
  term: string;
  selected: string;
  asOf: number;
  go: (href: string) => void;
  retry: () => void;
}) {
  const results = view.kind === "results" ? view.results : undefined;
  const row = (kind: string, id: string | number) => `${SEARCH_VALUE}${kind}:${id}`;
  return (
    <>
      <Command.Group heading="Products" className={group}>
        {results?.products.map((p) => (
          <Row
            key={p.id}
            value={row("product", p.id)}
            selected={selected}
            icon={Package}
            label={<Marked text={p.title} term={term} />}
            detail={p.match.text !== p.title && <>Listed as “<Marked text={p.match.text} term={term} />”</>}
            hint={p.category?.split(" > ").at(-1)}
            onSelect={() => go(`/products/${p.id}`)}
          />
        ))}
      </Command.Group>
      <VendorGroups
        heading="Stores"
        hits={results?.stores ?? []}
        row={(s) => (
          <Row
            key={s.id}
            value={row("store", s.id)}
            selected={selected}
            icon={Store}
            label={
              <>
                <Marked text={s.domain} term={term} />
                {s.top_product_id && TOP}
              </>
            }
            detail={s.match.field === "myshopify_domain" && <Marked text={s.match.text} term={term} />}
            hint={s.top_product_id ? <Crawled store={s} asOf={asOf} /> : "No products yet"}
            disabled={!s.top_product_id}
            onSelect={() => go(`/products/${s.top_product_id}`)}
          />
        )}
      />
      <VendorGroups
        heading="Suppliers"
        hits={results?.suppliers ?? []}
        row={(s) => (
          <Row
            key={s.id}
            value={row("supplier", s.id)}
            selected={selected}
            icon={Factory}
            label={
              <>
                <Marked text={s.name} term={term} />
                {s.top_product_id && TOP}
              </>
            }
            hint={s.top_product_id ? (PLATFORMS[s.platform] ?? s.platform) : "No products yet"}
            disabled={!s.top_product_id}
            onSelect={() => go(`/products/${s.top_product_id}`)}
          />
        )}
      />
      <Command.Group heading="Search" className={group}>
        {view.kind === "loading" && (
          <Row value={row("status", "loading")} selected={selected} icon={LoaderCircle} iconClassName="motion-safe:animate-spin" label="Searching products, stores and suppliers…" disabled />
        )}
        {view.kind === "empty" && (
          <Row value={row("status", "empty")} selected={selected} icon={SearchX} label={`No matches for “${term}”`} detail="Try a store domain, a supplier name or fewer words." disabled />
        )}
        {view.kind === "no-source" && (
          <>
            <Row value={row("status", "no-source")} selected={selected} icon={SearchX} label="Nothing collected yet" detail="Search fills in once the collectors have run." disabled />
            <Row value={row("status", "data-health")} selected={selected} icon={DatabaseZap} label="Open Data Health" hint={<CornerDownLeft className="size-3.5" aria-hidden />} onSelect={() => go("/admin/data-health")} />
          </>
        )}
        {view.kind === "error" && (
          <>
            <Row value={row("status", "error")} selected={selected} icon={TriangleAlert} iconClassName="text-warning" label="Search unavailable" detail="Commands still work." disabled />
            <Row value={row("status", "retry")} selected={selected} icon={RotateCw} label="Retry search" hint={<CornerDownLeft className="size-3.5" aria-hidden />} onSelect={retry} />
          </>
        )}
      </Command.Group>
    </>
  );
}

// Ctrl+K (vault Features/Command Palette & Search): global search over products, stores and suppliers (UX-9), and
// navigation to every §10 route, theme, sidebar and sign-out. Radix Dialog traps focus, closes on Esc and returns
// focus to whatever had it before opening; cmdk provides listbox semantics and arrow/Enter handling.
export function CommandPalette({
  open,
  onOpenChange,
  returnFocusRef,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Element focused before the palette opened (set by the shell); focus goes back there on close. */
  returnFocusRef: RefObject<HTMLElement | null>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const { collapsed, toggleCollapsed } = useShell();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const term = query.trim();
  const debounced = useDebounced(term, DEBOUNCE_MS);
  const search = $api.useQuery(
    "get",
    "/v1/search",
    { params: { query: { q: debounced } } },
    {
      enabled: useApiReady() && debounced.length >= MIN_QUERY,
      placeholderData: keepPreviousData, // the last results stay while the next query loads
      staleTime: 60_000,
      // A 4xx won't change on a retry.
      retry: (failures, error) => !(isProblem(error) && error.status < 500) && failures < 1,
    },
  );
  const view = searchView(term, debounced, search);
  // Kept results are timed from their own answer: a placeholder's dataUpdatedAt is 0 until the new query answers.
  const [asOf, setAsOf] = useState(0);
  if (search.dataUpdatedAt && search.dataUpdatedAt !== asOf) setAsOf(search.dataUpdatedAt);
  const busy = view.kind === "loading" || (view.kind === "results" && view.stale);
  const opensTop = /^search:(store|supplier):/.test(selected);

  const setOpen = (next: boolean) => {
    if (!next) {
      setQuery("");
      setSelected("");
    }
    onOpenChange(next);
  };
  const run: Run = { close: () => setOpen(false) };
  const go = (href: string) => {
    // A new route moves focus to its h1 (template.tsx), so don't pull it back to the old trigger.
    if (href !== pathname) returnFocusRef.current = null;
    run.close();
    router.push(href);
  };
  const nextTheme = resolvedTheme === "light" ? "dark" : "light";

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <m.div
                className="fixed inset-0 z-50 bg-overlay"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: { duration: duration.fast, ease: ease.out } }}
                exit={{ opacity: 0, transition: { duration: duration.fast, ease: ease.in } }}
              />
            </Dialog.Overlay>
            <Dialog.Content
              asChild
              forceMount
              aria-describedby={undefined}
              onCloseAutoFocus={(e) => {
                // Radix only restores focus to a Dialog.Trigger; this palette also opens from Ctrl+K.
                e.preventDefault();
                returnFocusRef.current?.focus();
              }}
              onEscapeKeyDown={(e) => {
                // First Esc clears the query, the second closes.
                if (query) {
                  e.preventDefault();
                  setQuery("");
                }
              }}
            >
              <m.div
                className="fixed inset-x-4 top-[12vh] z-60 mx-auto max-w-160 origin-top overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-dialog outline-none max-md:inset-x-0 max-md:top-0 max-md:h-dvh max-md:max-w-none max-md:rounded-none max-md:pt-[env(safe-area-inset-top)] max-md:pb-[env(safe-area-inset-bottom)]"
                initial={{ opacity: 0, scale: 0.98, y: -8 }}
                animate={{ opacity: 1, scale: 1, y: 0, transition: { duration: duration.base, ease: ease.out } }}
                exit={{ opacity: 0, transition: { duration: duration.fast, ease: ease.in } }}
              >
                <Dialog.Title className="sr-only">Command palette</Dialog.Title>
                <Command label="Command palette" value={selected} onValueChange={setSelected} filter={paletteFilter} loop className="flex h-full flex-col">
                  <div className="relative border-b border-border-subtle p-1.5 text-subtle-foreground">
                    {/* The search icon turns into a spinner while results load (no skeleton flash, vault UI States). */}
                    {busy ? (
                      <LoaderCircle
                        data-testid="palette-busy"
                        className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 motion-safe:animate-spin"
                        strokeWidth={1.5}
                        aria-hidden
                      />
                    ) : (
                      <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2" strokeWidth={1.5} aria-hidden />
                    )}
                    <Command.Input
                      value={query}
                      onValueChange={setQuery}
                      placeholder="Search products, stores, suppliers or commands…"
                      // Keeps the global focus ring (A11Y-01), drawn inset so it matches a row highlight: same height
                      // (40px, 44px on touch), 6px gutters and radius, with the icon, Esc and Close inside (imp-040).
                      className="h-10 w-full rounded-lg bg-transparent pr-14 pl-9 -outline-offset-2 pointer-coarse:h-11 text-title-3 text-foreground placeholder:text-subtle-foreground max-md:text-base"
                    />
                    <Kbd className="absolute top-1/2 right-3.5 -translate-y-1/2 max-md:hidden">Esc</Kbd>
                    <Dialog.Close className="absolute top-1/2 right-3.5 hit-area -translate-y-1/2 text-data font-medium text-muted-foreground md:hidden">
                      Close
                    </Dialog.Close>
                  </div>
                  <p role="status" aria-live="polite" className="sr-only">
                    {announce(view, term)}
                  </p>
                  <LayoutGroup id="palette">
                    <Command.List
                      aria-busy={busy}
                      className="max-h-105 flex-1 scroll-py-1.5 overflow-y-auto overscroll-contain py-1.5 max-md:max-h-none">
                      <Command.Empty className="px-6 py-8 text-center text-data text-muted-foreground">
                        No command matches “{query}”. Type 2 or more characters to search products, stores and suppliers.
                      </Command.Empty>

                      <Command.Group heading="Go to" className={group}>
                        {allNavItems.map((nav) => (
                          <Row
                            key={nav.href}
                            value={`go ${nav.href}`}
                            selected={selected}
                            icon={nav.icon}
                            label={nav.label}
                            keywords={[nav.label, nav.href]}
                            hint={isBuilt(nav) ? <CornerDownLeft className="size-3.5" aria-hidden /> : `Phase ${nav.phase}`}
                            onSelect={() => go(nav.href)}
                          />
                        ))}
                      </Command.Group>

                      <Command.Group heading="Preferences" className={group}>
                        <Row
                          value="theme-toggle"
                          selected={selected}
                          icon={nextTheme === "light" ? Sun : Moon}
                          label={`Switch to ${nextTheme} theme`}
                          keywords={["theme", "dark", "light", "appearance"]}
                          onSelect={() => setTheme(nextTheme)}
                        />
                        <Row value="theme-system" selected={selected} icon={Monitor} label="Use system theme" keywords={["theme", "appearance"]} onSelect={() => setTheme("system")} />
                        <Row
                          value="sidebar-toggle"
                          selected={selected}
                          icon={PanelLeft}
                          label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                          keywords={["sidebar", "rail"]}
                          hint={<Kbd>[</Kbd>}
                          onSelect={() => {
                            run.close();
                            toggleCollapsed();
                          }}
                        />
                      </Command.Group>

                      {!authBypass && (
                        <Command.Group heading="Account" className={group}>
                          <SignOutRow selected={selected} run={run} />
                        </Command.Group>
                      )}

                      {view.kind !== "off" && (
                        <SearchGroups view={view} term={term} selected={selected} asOf={asOf} go={go} retry={() => void search.refetch()} />
                      )}
                    </Command.List>
                  </LayoutGroup>
                  <div className="flex h-10 shrink-0 items-center gap-4 border-t border-border-subtle px-4 text-label text-subtle-foreground max-md:hidden">
                    <span className="inline-flex items-center gap-1.5">
                      <Kbd>↑</Kbd>
                      <Kbd>↓</Kbd> Navigate
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Kbd>↵</Kbd> {opensTop ? "Open top product" : "Open"}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <Kbd>Esc</Kbd> Close
                    </span>
                  </div>
                </Command>
              </m.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
