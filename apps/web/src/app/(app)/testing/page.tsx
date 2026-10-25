import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { BoardSkeleton, TestingBoard } from "./board";

export const metadata: Metadata = { title: "Testing" };

// WF-5b: the header renders on the server; the board reads and moves tests through /v1/tests on the client.
export default function TestingPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Testing" description="Your product tests from idea to winner or kill. Move a card with its menu or drag it; a kill needs a reason." />
      {/* The board reads ?test= (useSearchParams), so the static page renders its skeleton until the client takes over. */}
      <Suspense fallback={<BoardSkeleton />}>
        <TestingBoard />
      </Suspense>
    </div>
  );
}
