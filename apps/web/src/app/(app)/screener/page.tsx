import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { Screener } from "./screener";

export const metadata: Metadata = { title: "Screener" };

// WF-1b. The header renders on the server; the screen lives in the URL and its rows come from GET /v1/screener on the
// client, like Discover.
export default function ScreenerPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Screener" description="Filter every product on any metric and save the screens you reuse." />
      <Suspense>
        <Screener />
      </Suspense>
    </div>
  );
}
