import { Suspense } from "react";
import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { AmazonRanks } from "./amazon-ranks";

export const metadata: Metadata = { title: "Amazon ranks" };

// AMZ-1b (DEC-286): the owner's imported Amazon Best Sellers and Movers & Shakers lists (DEC-279).
export default function AmazonPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader
        title="Amazon ranks"
        description="Best Sellers and Movers & Shakers ranks from the Amazon CSV files you import. A rank compares products within its own category and list only."
      />
      <Suspense>
        <AmazonRanks />
      </Suspense>
    </div>
  );
}
