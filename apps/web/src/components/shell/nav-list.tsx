"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { LayoutGroup } from "motion/react";
import * as m from "motion/react-m";

import { DataHealthNavBadge } from "@/components/data-health/nav-badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { spring } from "@/lib/motion";
import { isBuilt, navGroups, resolveRoute, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

// In the desktop sidebar, labels and chips only show when it is expanded: at xl and not collapsed.
// Below xl (and when collapsed) it is a 56px icon rail with tooltips; labels stay for screen readers.
export const whenExpanded = "hidden xl:group-data-[collapsed=false]/sidebar:flex";
export const whenRail = "xl:group-data-[collapsed=false]/sidebar:hidden";
const labelRail = "sr-only xl:group-data-[collapsed=false]/sidebar:not-sr-only";

/** Tooltip shown only while the sidebar is a rail; always controlled, so toggling the rail is safe. */
export function RailTooltip({ rail, label, children }: { rail: boolean; label: React.ReactNode; children: React.ReactElement }) {
  const [open, setOpen] = useState(false);
  return (
    <Tooltip open={rail && open} onOpenChange={setOpen}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

export function useActiveHref(): string | undefined {
  return resolveRoute(usePathname())?.activeHref;
}

export function NavLink({
  item,
  active,
  rail,
  variant,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  rail: boolean;
  variant: "sidebar" | "sheet";
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const built = isBuilt(item);
  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative hit-area flex h-(--nav-item-h) items-center gap-2 rounded-md px-2 text-body text-sidebar-foreground transition-colors duration-(--duration-fast) ease-standard",
        "hover:bg-accent hover:text-foreground aria-[current=page]:font-medium aria-[current=page]:text-foreground aria-[current=page]:hover:bg-transparent",
        variant === "sidebar" && "max-xl:justify-center group-data-[collapsed=true]/sidebar:justify-center",
      )}
    >
      {active && (
        // Shared active pill: slides between items (pattern 3), jumps under reduced motion.
        <m.span layoutId="nav-active" transition={spring.snappy} className="absolute inset-0 rounded-md bg-accent before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-brand" />
      )}
      <Icon className="relative size-4.5 shrink-0" strokeWidth={1.5} aria-hidden />
      <span className={cn("relative truncate", variant === "sidebar" && labelRail)}>{item.label}</span>
      {!built && (
        <span className={cn("relative ml-auto items-center text-micro font-medium text-subtle-foreground", variant === "sidebar" ? whenExpanded : "flex")}>
          <span aria-hidden>{item.noSource ? "No source yet" : `P${item.phase}`}</span>
          <span className="sr-only">{item.noSource ? ", no source yet" : `, arrives in Phase ${item.phase}`}</span>
        </span>
      )}
      {built && item.href === "/admin/data-health" && (
        <DataHealthNavBadge expandedClass={variant === "sidebar" ? whenExpanded : "flex"} railClass={variant === "sidebar" ? whenRail : undefined} />
      )}
    </Link>
  );

  if (variant === "sheet") return link;
  return (
    <RailTooltip
      rail={rail}
      label={
        <>
          {item.label}
          {!built && <span className="text-subtle-foreground"> · {item.noSource ? "No source yet" : `Phase ${item.phase}`}</span>}
        </>
      }
    >
      {link}
    </RailTooltip>
  );
}

export function NavList({
  variant,
  rail = false,
  onNavigate,
}: {
  variant: "sidebar" | "sheet";
  rail?: boolean;
  onNavigate?: () => void;
}) {
  const activeHref = useActiveHref();
  return (
    // Each instance namespaces its layoutId, so the sidebar and the sheet never share a pill.
    <LayoutGroup id={variant}>
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {navGroups.map((group) => (
          <div key={group.label ?? "home"} className="flex flex-col gap-0.5">
            {group.label && (
              <>
                <div className={cn("px-2 pt-3 pb-1.5 text-label font-medium text-subtle-foreground", variant === "sidebar" && whenExpanded)}>
                  {group.label}
                </div>
                {variant === "sidebar" && <div aria-hidden className={cn("mx-2 my-2 h-px bg-border-subtle", whenRail)} />}
              </>
            )}
            <ul aria-label={group.label ?? "Home"} className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.href}>
                  <NavLink item={item} active={item.href === activeHref} rail={rail} variant={variant} onNavigate={onNavigate} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </LayoutGroup>
  );
}
