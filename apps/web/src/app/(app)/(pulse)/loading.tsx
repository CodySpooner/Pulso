import { Skeleton } from "@/components/ui/skeleton";

const spans = ["xl:col-span-7", "xl:col-span-5", "xl:col-span-7", "xl:col-span-5", "md:col-span-2 xl:col-span-12"];

// Skeleton sized to the rendered Daily Pulse at each breakpoint (measured), so nothing shifts when the
// page arrives (vault Design/UI States).
export default function DailyPulseLoading() {
  return (
    <div aria-busy="true" className="flex flex-col gap-6">
      <span className="sr-only" role="status">
        Loading Daily Pulse
      </span>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <Skeleton className="h-8 w-44" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </div>
        <Skeleton className="h-8 w-44" />
      </div>
      <Skeleton className="h-90 rounded-xl sm:h-111 md:h-71 lg:h-66 xl:h-61" />
      <div className="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-6 xl:grid-cols-12">
        {spans.map((span, i) => (
          <Skeleton key={i} className={`h-58 rounded-xl md:h-57.5 ${span}`} />
        ))}
      </div>
    </div>
  );
}
