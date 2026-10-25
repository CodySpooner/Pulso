import { Suspense } from "react";
import type { Metadata } from "next";
import { Lock } from "lucide-react";

import { PageHeader } from "@/components/pulso/page-header";

import { GooglePopular } from "./google-popular";

export const metadata: Metadata = { title: "Google popular" };

// P2-29 b (DEC-272): the owner's Merchant Center Popular products report. Signed-in only, never a public page (DEC-267 f).
export default function GooglePopularPage() {
  return (
    <div className="flex w-full flex-col gap-5">
      <PageHeader
        title="Google popular"
        description="What US shoppers bought on Google each week, from your Merchant Center report. Big brands are hidden so dropshippable products surface; hide any other brand from its row."
      />
      <Suspense>
        <GooglePopular />
      </Suspense>
      <p className="flex items-start gap-1.5 text-label text-subtle-foreground">
        <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        Google allows Popular products data for your business&apos;s internal use only: don&apos;t resell, publish or share it.
      </p>
    </div>
  );
}
