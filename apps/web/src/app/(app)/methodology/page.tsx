import type { Metadata } from "next";

import { resolveRoute } from "@/lib/nav";

import { Methodology } from "./methodology";
import { methodology } from "./model";

export const metadata: Metadata = { title: "Methodology" };

// MT-1 (DEC-313): rendered on the server from the committed export of the scoring code; no request, no API.
export default function MethodologyPage() {
  return <Methodology doc={methodology} description={resolveRoute("/methodology")!.item.summary} />;
}
