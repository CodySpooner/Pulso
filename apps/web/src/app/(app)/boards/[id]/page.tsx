import { Suspense } from "react";
import type { Metadata } from "next";

import { BoardSkeleton, BoardView } from "./board";

export const metadata: Metadata = { title: "Board" };

// WF-3b: one board's cards. The board and its cards come from /v1/boards on the client; the view reads ?view=.
export default async function Page({ params }: PageProps<"/boards/[id]">) {
  return (
    <Suspense fallback={<BoardSkeleton />}>
      <BoardView id={(await params).id} />
    </Suspense>
  );
}
