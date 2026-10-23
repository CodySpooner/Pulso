"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { FocusEvent } from "react";
import { Menu, Search } from "lucide-react";

import { DataHealthNavBadge } from "@/components/data-health/nav-badge";
import { Logo } from "@/components/pulso/logo";
import { ModKey } from "@/components/pulso/mod-key";
import { StatusDot } from "@/components/pulso/status-dot";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { resolveRoute } from "@/lib/nav";

import { useShell } from "./app-shell";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";
import { WorkspaceChip } from "./workspace-chip";


function Breadcrumbs() {
  const route = resolveRoute(usePathname());
  if (!route?.group) return null;
  return (
    <nav aria-label="Breadcrumb" className="hidden min-w-0 lg:block">
      <ol className="flex items-center gap-1.5 text-data whitespace-nowrap text-muted-foreground">
        {route.group && (
          <>
            <li>{route.detail ? <Link href={route.activeHref} className="relative hit-area rounded-sm hover:text-foreground">{route.group}</Link> : route.group}</li>
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

// The menu sheet and the palette hand focus back to their button on close. After a tap or click that focus isn't
// :focus-visible, so this skips Radix's open-on-focus and leaves no tooltip over the page; keyboard focus still opens it.
function keyboardFocusOnly(e: FocusEvent) {
  if (!e.currentTarget.matches(":focus-visible")) e.preventDefault();
}

// Top bar (vault Design/App Shell & Navigation): breadcrumbs, search trigger, market and freshness chips,
// workspace chip (/v1/me), theme toggle and the Clerk user menu. Below 1024px: menu button and the logo (the page h1 names the page).
export function Topbar() {
  const { openPalette, openNav } = useShell();

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-border-subtle bg-background px-4 pt-[env(safe-area-inset-top)] md:px-6 lg:static lg:h-12 lg:pt-0">
      <Tooltip>
        <TooltipTrigger asChild onFocus={keyboardFocusOnly}>
          <Button variant="ghost" size="icon" className="-ml-2 hidden md:inline-flex lg:hidden" onClick={openNav}>
            <Menu strokeWidth={1.5} aria-hidden />
            {/* imp-093: no sidebar or tab bar at 768–1023px, so the menu button carries the DH-3 count. Text, not
                aria-label, so the badge's sr-only wording joins the name. */}
            <span className="sr-only">Open menu</span>
            <DataHealthNavBadge expandedClass="absolute -top-1.5 left-1/2 ml-1 flex" />
          </Button>
        </TooltipTrigger>
        <TooltipContent align="start">Open menu</TooltipContent>
      </Tooltip>
      <Link href="/" aria-label="Pulso, go to Daily Pulse" className="relative hit-area flex h-8 items-center rounded-md lg:hidden">
        <Logo />
      </Link>
      <Breadcrumbs />

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={openPalette}
          aria-keyshortcuts="Control+K Meta+K"
          className="relative hit-area hidden h-8 w-64 items-center gap-2 rounded-md border border-border bg-card pr-1.5 pl-2 text-data text-subtle-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong lg:flex xl:w-72"
        >
          <Search className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />
          <span className="truncate">Search or run a command…</span>
          <ModKey className="ml-auto" />
        </button>
        <Tooltip>
          <TooltipTrigger asChild onFocus={keyboardFocusOnly}>
            <Button variant="ghost" size="icon" className="hidden md:inline-flex lg:hidden" aria-label="Open command palette" onClick={openPalette}>
              <Search strokeWidth={1.5} aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Open command palette <ModKey className="ml-1" />
          </TooltipContent>
        </Tooltip>

        <span className="hidden h-8 items-center rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground xl:inline-flex">
          US · USD
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              href="/admin/data-health"
              className="relative hit-area hidden h-8 items-center gap-1.5 rounded-md border border-border-subtle px-2 text-label font-medium whitespace-nowrap text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong md:inline-flex"
            >
              <StatusDot state="disabled" />
              Data as of —
            </Link>
          </TooltipTrigger>
          <TooltipContent className="max-w-60">Collectors start in Phase 1. Then every number shows its source and an “as of” time.</TooltipContent>
        </Tooltip>
        <WorkspaceChip />

        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
