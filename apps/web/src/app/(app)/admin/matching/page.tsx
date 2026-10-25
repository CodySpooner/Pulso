import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { MatchingQueue } from "./matching-queue";

export const metadata: Metadata = { title: "Matching" };

// UX-1. The header renders on the server; the queue reads and decides through /v1/admin/matching on the client.
export default function MatchingPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader
        title="Matching"
        description="Accept or reject possible matches between listings. Every decision is logged, and the matcher never undoes one."
      />
      <MatchingQueue />
    </div>
  );
}
