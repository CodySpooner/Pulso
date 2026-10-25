import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { AlertsInbox, Loading } from "./inbox";

export const metadata: Metadata = { title: "Alerts" };

// WF-4b (DEC-333): the alerts inbox. The rule builder and the Rules tab are WF-4c.
export default function AlertsPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Alerts" description="Each alert fires once when a supplier’s price, freight or stock crosses one of your rules, with the numbers that crossed it." />
      {/* The inbox reads its filters from the URL (useSearchParams), so the static page shows the skeleton first. */}
      <Suspense fallback={<Loading />}>
        <AlertsInbox />
      </Suspense>
    </div>
  );
}
