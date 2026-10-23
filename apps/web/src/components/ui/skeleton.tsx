import { cn } from "@/lib/utils";

// Appears after 150ms so fast loads never flash, then shimmers (vault Design/Motion System pattern 14).
// The global reduced-motion clamp turns it into a static block.
// The sweep is the middle third of a box three bars wide, so the box always covers the bar: a shimmer clipped to
// nothing made Chrome score a skeleton moved by a panel above as a jump from the viewport's origin (p1-53).
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn(
        "relative overflow-hidden rounded-sm bg-skeleton opacity-0 animate-[appear_var(--duration-fast)_var(--skeleton-delay)_forwards]",
        "after:absolute after:inset-y-0 after:-left-full after:w-[300%] after:-translate-x-1/3 after:bg-linear-to-r after:from-transparent after:from-[33.333%] after:via-skeleton-highlight after:to-transparent after:to-[66.667%] after:animate-[shimmer_var(--duration-shimmer)_var(--ease-in-out)_infinite]",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
