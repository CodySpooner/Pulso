"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Search } from "lucide-react";

import { Logo } from "@/components/pulso/logo";
import { ModKey } from "@/components/pulso/mod-key";
import { StatusDot } from "@/components/pulso/status-dot";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { resolveRoute } from "@/lib/nav";

import { useShell } from "./app-shell";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";


function Breadcrumbs() {
  const route = resolveRoute(usePathname());
  if (!route?.group) return null;
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
// theme toggle and the Clerk user menu. Below 1024px: menu button and the logo (the page h1 names the page).
export function Topbar() {
  const { openPalette, openNav } = useShell();

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border-subtle bg-background px-4 pt-[env(safe-area-inset-top)] md:px-6 lg:static lg:h-12 lg:pt-0">
      <Button variant="ghost" size="icon" className="-ml-2 hidden md:inline-flex lg:hidden" aria-label="Open menu" onClick={openNav}>
        <Menu strokeWidth={1.5} aria-hidden />
      </Button>
      <Link href="/" aria-label="Pulso, go to Daily Pulse" className="flex h-8 items-center rounded-md lg:hidden">
        <Logo />
      </Link>
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
          <ModKey className="ml-auto" />
        </button>
        <Button variant="ghost" size="icon" className="hidden md:inline-flex lg:hidden" aria-label="Open command palette" onClick={openPalette}>
          <Search strokeWidth={1.5} aria-hidden />
        </Button>

        <span className="hidden h-8 items-center rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground xl:inline-flex">
          US · USD
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/admin/data-health"
              className="hidden h-8 items-center gap-1.5 rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong md:inline-flex"
            >
              <StatusDot state="disabled" />
              Data as of —
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
