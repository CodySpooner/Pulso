import { Skeleton } from "@/components/ui/skeleton";

import { CardsSkeleton } from "./cards";

// The header and the card grid in their loaded shapes, so nothing shifts when the pulse arrives (vault Design/UI States).
export default function DailyPulseLoading() {
  return (
    <div aria-busy="true" className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1">
          <Skeleton className="h-8 w-44" />
          <Skeleton className="h-4 w-72 max-w-full" />
        </div>
        <Skeleton className="h-8 w-52" />
      </div>
      <CardsSkeleton />
    </div>
  );
}
