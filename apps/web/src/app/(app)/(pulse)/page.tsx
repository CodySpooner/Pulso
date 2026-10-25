import { Suspense } from "react";
import type { Metadata } from "next";

import { DailyPulse } from "./pulse";
import DailyPulseLoading from "./loading";

export const metadata: Metadata = { title: "Daily Pulse" };

// WF-6b (DEC-342): the day comes from the URL (useSearchParams), so the static page shows the skeleton first.
export default function DailyPulsePage() {
  return (
    <Suspense fallback={<DailyPulseLoading />}>
      <DailyPulse />
    </Suspense>
  );
}
