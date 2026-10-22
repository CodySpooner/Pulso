import { cn } from "@/lib/utils";

// Appears after 150ms so fast loads never flash, then shimmers (vault Design/Motion System pattern 14).
// The global reduced-motion clamp turns it into a static block.
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn(
        "relative overflow-hidden rounded-sm bg-skeleton opacity-0 animate-[appear_var(--duration-fast)_var(--skeleton-delay)_forwards]",
        "after:absolute after:inset-0 after:-translate-x-full after:bg-linear-to-r after:from-transparent after:via-skeleton-highlight after:to-transparent after:animate-[shimmer_var(--duration-shimmer)_var(--ease-in-out)_infinite]",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
