import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { Discover } from "./discover";

export const metadata: Metadata = { title: "Discover" };

// UX-2. The header renders on the server; the feed reads its state from the URL and its data from GET /v1/products
// on the client, like Data Health.
export default function DiscoverPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Discover" description="Products across your sources. Every number names its source and how old it is." />
      <Suspense>
        <Discover />
      </Suspense>
    </div>
  );
}
