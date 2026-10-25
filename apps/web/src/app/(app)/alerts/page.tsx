import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { Loading } from "./inbox";
import { Alerts } from "./rules";

export const metadata: Metadata = { title: "Alerts" };

// WF-4b (DEC-333): the alerts inbox and archive; WF-4c (DEC-339): the Rules tab.
export default function AlertsPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Alerts" description="Each alert fires once when a supplier’s price, freight or stock crosses one of your rules, with the numbers that crossed it." />
      {/* The views read their filters from the URL (useSearchParams), so the static page shows the skeleton first. */}
      <Suspense fallback={<Loading />}>
        <Alerts />
      </Suspense>
    </div>
  );
}
