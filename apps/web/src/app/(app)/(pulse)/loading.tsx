import { Skeleton } from "@/components/ui/skeleton";

const spans = ["xl:col-span-7", "xl:col-span-5", "xl:col-span-6", "xl:col-span-6", "md:col-span-2 xl:col-span-12"];

// Skeleton matching the final Daily Pulse layout, so nothing shifts when it renders (vault Design/UI States).
export default function DailyPulseLoading() {
  return (
    <div aria-busy="true" className="flex flex-col gap-6">
      <span className="sr-only" role="status">
        Loading Daily Pulse
      </span>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-44" />
        <Skeleton className="h-4 w-72 max-w-full" />
      </div>
      <Skeleton className="h-64 rounded-xl sm:h-52" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:gap-6 xl:grid-cols-12">
        {spans.map((span) => (
          <Skeleton key={span} className={`h-60 rounded-xl ${span}`} />
        ))}
      </div>
    </div>
  );
}
