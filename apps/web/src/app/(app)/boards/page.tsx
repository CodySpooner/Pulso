import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { BoardsIndex, TilesSkeleton } from "./boards-index";

export const metadata: Metadata = { title: "Boards" };

// WF-3b: the header renders on the server; the tiles read and create boards through /v1/boards on the client.
export default function BoardsPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader title="Boards" description="Collections of product ideas: a niche, a season, a batch to test. Open a board to order its cards and write a note on each." />
      {/* The filter reads ?archived= (useSearchParams), so the static page renders its skeleton until the client takes over. */}
      <Suspense fallback={<TilesSkeleton />}>
        <BoardsIndex />
      </Suspense>
    </div>
  );
}
