import { cn } from "@/lib/utils";

export type StatusDotState = "ok" | "warning" | "failed" | "disabled";

// Always paired with a text label. `ok` is neutral (a normal state is not news); `disabled` is hollow
// and dashed. The pulsing `running` state arrives with real job state in Phase 1 (vault Component Inventory).
export function StatusDot({ state, className }: { state: StatusDotState; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-block size-2 shrink-0 rounded-full",
        state === "ok" && "bg-subtle-foreground",
        state === "warning" && "bg-warning",
        state === "failed" && "bg-negative",
        state === "disabled" && "border border-dashed border-subtle-foreground",
        className,
      )}
    />
  );
}
