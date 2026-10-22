"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { Logo, LogoMark } from "@/components/pulso/logo";
import { Kbd } from "@/components/ui/kbd";
import { settingsItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

import { useShell } from "./app-shell";
import { CollectorHostStatus } from "./collector-host-status";
import { NavLink, NavList, RailTooltip, useActiveHref, whenExpanded, whenRail } from "./nav-list";

const XL = "(min-width: 1280px)";
const subscribeXl = (onChange: () => void) => {
  const query = window.matchMedia(XL);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
};

/** True when the desktop sidebar shows as the 56px icon rail (below xl, or collapsed by the user). */
function useRail(collapsed: boolean): boolean {
  const xl = useSyncExternalStore(subscribeXl, () => window.matchMedia(XL).matches, () => true);
  return collapsed || !xl;
}

// Desktop sidebar (≥1024px). Collapsing reflows the content once with no width animation (Motion System
// pattern 11); the labels are hidden with CSS, so resizing across breakpoints never animates either.
export function Sidebar() {
  const { collapsed, toggleCollapsed } = useShell();
  const rail = useRail(collapsed);
  const activeHref = useActiveHref();

  return (
    <aside
      data-collapsed={collapsed}
      className="group/sidebar sticky top-0 hidden h-dvh w-14 shrink-0 flex-col bg-sidebar py-3 lg:flex xl:w-60 xl:data-[collapsed=true]:w-14"
    >
      <div className="flex h-9 items-center px-2 pb-3">
        <Link href="/" aria-label="Pulso, go to Daily Pulse" className="flex h-8 items-center rounded-md px-2 max-xl:mx-auto group-data-[collapsed=true]/sidebar:mx-auto">
          <span className={cn("items-center", whenExpanded)}>
            <Logo />
          </span>
          <LogoMark className={cn("size-5 text-brand", whenRail)} />
        </Link>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4 [scrollbar-width:thin] mask-b-from-[calc(100%-1.5rem)]">
        <NavList variant="sidebar" rail={rail} />
      </div>

      <div className="flex flex-col gap-0.5 border-t border-sidebar-border px-2 pt-3">
        <CollectorHostStatus rail={rail} />
        <NavLink item={settingsItem} active={activeHref === settingsItem.href} rail={rail} variant="sidebar" />
        <RailTooltip
          rail={rail}
          label={
            <>
              Expand sidebar <Kbd className="ml-1">[</Kbd>
            </>
          }
        >
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-keyshortcuts="["
            className="hidden h-(--nav-item-h) items-center gap-2 rounded-md px-2 text-body text-sidebar-foreground transition-colors duration-(--duration-fast) ease-standard hover:bg-accent hover:text-foreground xl:flex xl:group-data-[collapsed=true]/sidebar:justify-center"
          >
            {collapsed ? <PanelLeftOpen className="size-4.5" strokeWidth={1.5} aria-hidden /> : <PanelLeftClose className="size-4.5" strokeWidth={1.5} aria-hidden />}
            <span className={cn("flex-1 items-center justify-between", whenExpanded)}>
              Collapse <Kbd>[</Kbd>
            </span>
          </button>
        </RailTooltip>
      </div>
    </aside>
  );
}
