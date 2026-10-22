import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

// EmptyState and ErrorState share one anatomy (vault Design/Component Inventory, UI States): a 40px icon
// tile, a title, one or two sentences, at most one primary action.
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  tone = "neutral",
  size = "md",
  headingLevel: Heading = "h3",
  className,
}: {
  icon: LucideIcon;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  tone?: "neutral" | "error";
  size?: "sm" | "md";
  headingLevel?: "h1" | "h2" | "h3";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-2 text-center", size === "md" ? "px-6 py-10" : "px-4 py-8", className)}>
      <div
        className={cn(
          "mb-1 grid size-10 place-items-center rounded-lg border border-border bg-secondary",
          tone === "error" ? "text-negative" : "text-muted-foreground",
        )}
      >
        <Icon className="size-5" strokeWidth={1.5} aria-hidden />
      </div>
      <Heading tabIndex={Heading === "h1" ? -1 : undefined} className={cn("text-foreground outline-none", size === "md" ? "text-title-3 font-semibold" : "text-body font-medium")}>
        {title}
      </Heading>
      {children && <div className="max-w-[46ch] text-data text-muted-foreground">{children}</div>}
      {action && <div className="mt-3 flex flex-wrap items-center justify-center gap-2">{action}</div>}
    </div>
  );
}
