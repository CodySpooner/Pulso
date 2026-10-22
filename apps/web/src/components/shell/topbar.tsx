"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Menu, Search } from "lucide-react";

import { LogoMark } from "@/components/pulso/logo";
import { StatusDot } from "@/components/pulso/status-dot";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { resolveRoute } from "@/lib/nav";

import { useShell } from "./app-shell";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

const noop = () => () => {};
/** "⌘" on macOS, "Ctrl" elsewhere. The server renders "Ctrl". */
export function useModKey(): string {
  return useSyncExternalStore(noop, () => (/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl"), () => "Ctrl");
}

function Breadcrumbs() {
  const route = resolveRoute(usePathname());
  if (!route) return null;
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 lg:block">
      <ol className="flex items-center gap-1.5 text-data whitespace-nowrap text-muted-foreground">
        {route.group && (
          <>
            <li>{route.detail ? <Link href={route.activeHref} className="rounded-sm hover:text-foreground">{route.group}</Link> : route.group}</li>
            <li aria-hidden className="text-subtle-foreground">/</li>
          </>
        )}
        <li aria-current="page" className="truncate font-medium text-foreground">
          {route.item.label}
        </li>
      </ol>
    </nav>
  );
}

// Top bar (vault Design/App Shell & Navigation): breadcrumbs, search trigger, market and freshness chips,
// theme toggle and the Clerk user menu. Below 1024px: menu button, mark and page title.
export function Topbar() {
  const { openPalette, openNav } = useShell();
  const route = resolveRoute(usePathname());
  const mod = useModKey();

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border-subtle bg-background px-4 pt-[env(safe-area-inset-top)] lg:static lg:h-12 lg:pt-0">
      <Button variant="ghost" size="icon" className="-ml-2 hidden md:inline-flex lg:hidden" aria-label="Open menu" onClick={openNav}>
        <Menu strokeWidth={1.5} aria-hidden />
      </Button>
      <Link href="/" aria-label="Pulso, go to Daily Pulse" className="grid size-8 place-items-center rounded-md lg:hidden">
        <LogoMark className="size-5 text-brand" />
      </Link>
      <span className="min-w-0 truncate text-title-3 font-semibold text-foreground lg:hidden">{route?.item.label ?? "Pulso"}</span>
      <Breadcrumbs />

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={openPalette}
          aria-keyshortcuts="Control+K Meta+K"
          className="hidden h-8 w-64 items-center gap-2 rounded-md border border-border bg-card pr-1.5 pl-2 text-data text-subtle-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong lg:flex xl:w-72"
        >
          <Search className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          <span className="truncate">Search or run a command…</span>
          <Kbd className="ml-auto">{mod} K</Kbd>
        </button>
        <Button variant="ghost" size="icon" className="hidden md:inline-flex lg:hidden" aria-label="Open command palette" onClick={openPalette}>
          <Search strokeWidth={1.5} aria-hidden />
        </Button>

        <span className="hidden h-7 items-center rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground xl:inline-flex">
          US · USD
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/admin/data-health"
              className="hidden h-7 items-center gap-1.5 rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong md:inline-flex"
            >
              <StatusDot state="disabled" className="size-1.5" />
              No data yet
            </Link>
          </TooltipTrigger>
          <TooltipContent className="max-w-60">Collectors start in Phase 1. Then every number shows its source and an “as of” time.</TooltipContent>
        </Tooltip>

        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
