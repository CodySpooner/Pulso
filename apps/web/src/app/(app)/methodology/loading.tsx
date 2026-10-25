import { Skeleton } from "@/components/ui/skeleton";

// The page is static, so this shows only while a client navigation fetches it (vault Design/UI States).
export default function MethodologyLoading() {
  return (
    <div aria-busy="true" className="flex w-full max-w-280 flex-col gap-6">
      <span className="sr-only" role="status">
        Loading Methodology
      </span>
      <div className="flex flex-col gap-1">
        <Skeleton className="h-8 w-44" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_12rem]">
        <div className="flex flex-col gap-6">
          <Skeleton className="h-160 rounded-xl" />
          <Skeleton className="h-48 rounded-xl" />
        </div>
        <Skeleton className="hidden h-72 rounded-xl lg:block" />
      </div>
    </div>
  );
}
