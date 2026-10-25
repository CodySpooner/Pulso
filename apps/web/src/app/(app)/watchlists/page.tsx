import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { Watchlists } from "./watchlists";

export const metadata: Metadata = { title: "Watchlists" };

// WF-2b: the header renders on the server; the lists and their products come from /v1/watchlists on the client.
export default function WatchlistsPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Watchlists" description="Products you're keeping an eye on, with the numbers that move. ★ adds a product to Main." />
      <Suspense>
        <Watchlists />
      </Suspense>
    </div>
  );
}
