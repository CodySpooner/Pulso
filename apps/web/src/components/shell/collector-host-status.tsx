"use client";

import Link from "next/link";

import { useHost } from "@/components/data-health/api";
import { hostState, type HostState } from "@/components/data-health/model";
import { StatusDot, type StatusDotState } from "@/components/pulso/status-dot";
import { formatAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

import { RailTooltip, whenExpanded } from "./nav-list";

const hostDot: Record<HostState, { dot: StatusDotState; label: string }> = {
  online: { dot: "ok", label: "Online" },
  late: { dot: "warning", label: "Late" },
  offline: { dot: "failed", label: "Offline" },
  none: { dot: "disabled", label: "No heartbeat yet" },
};

// Sidebar footer status for the home-PC collector host, from the latest heartbeat (GET /v1/admin/host,
// vault Design/App Shell & Navigation): amber after 15 min without one, red after 2 h.
export function CollectorHostStatus({
  rail,
  variant = "sidebar",
  onNavigate,
}: {
  rail: boolean;
  variant?: "sidebar" | "sheet";
  onNavigate?: () => void;
}) {
  const host = useHost();
  const state = host.data ? hostDot[hostState(host.data, host.dataUpdatedAt)] : null;
  const at = host.data?.latest_heartbeat?.at;
  const dot: StatusDotState = host.isError ? "warning" : (state?.dot ?? "disabled");
  const line = host.isError ? "Can't reach the API" : !state ? "Checking…" : at ? `${state.label} · ${formatAgo(at, host.dataUpdatedAt)}` : state.label;

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
        <StatusDot state={dot} />
      </span>
      <span className={cn("min-w-0 flex-col", variant === "sidebar" ? whenExpanded : "flex")}>
        <span className="font-medium text-foreground">Collector host</span>
        <span className="text-subtle-foreground">{line}</span>
      </span>
      {variant === "sidebar" && <span className="sr-only xl:group-data-[collapsed=false]/sidebar:hidden">Collector host: {line}</span>}
    </Link>
  );
  if (variant === "sheet") return link;
  return (
    <RailTooltip rail={rail} label={`Collector host · ${line}`}>
      {link}
    </RailTooltip>
  );
}
