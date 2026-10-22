"use client";

import Link from "next/link";

import { StatusDot } from "@/components/pulso/status-dot";
import { cn } from "@/lib/utils";

import { RailTooltip, whenExpanded } from "./nav-list";

// Sidebar footer status for the home-PC collector host. Real heartbeat data arrives with Phase 1
// (vault Design/App Shell & Navigation); until then it says plainly that there is no host yet.
export function CollectorHostStatus({
  rail,
  variant = "sidebar",
  onNavigate,
}: {
  rail: boolean;
  variant?: "sidebar" | "sheet";
  onNavigate?: () => void;
}) {
  const link = (
    <Link
      href="/admin/data-health"
      onClick={onNavigate}
      className={cn(
        "flex items-start gap-2 rounded-md px-2 py-2 text-label transition-colors duration-(--duration-fast) ease-standard hover:bg-accent",
        variant === "sidebar" && "max-xl:justify-center group-data-[collapsed=true]/sidebar:justify-center",
      )}
    >
      <span className="grid h-4 w-4.5 shrink-0 place-items-center">
        <StatusDot state="disabled" />
      </span>
      <span className={cn("min-w-0 flex-col", variant === "sidebar" ? whenExpanded : "flex")}>
        <span className="font-medium text-foreground">Collector host</span>
        <span className="text-subtle-foreground">None yet · arrives in Phase 1</span>
      </span>
      {variant === "sidebar" && <span className="sr-only xl:group-data-[collapsed=false]/sidebar:hidden">Collector host: none yet</span>}
    </Link>
  );
  if (variant === "sheet") return link;
  return (
    <RailTooltip rail={rail} label="No collector host yet · Phase 1">
      {link}
    </RailTooltip>
  );
}
