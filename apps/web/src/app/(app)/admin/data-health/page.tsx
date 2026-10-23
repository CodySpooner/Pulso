import type { Metadata } from "next";

import { DataHealth } from "@/components/data-health/data-health";

export const metadata: Metadata = { title: "Data Health" };

// DH-2. Admin-only like every route in (app); the data comes from the DH-1 API on the client.
export default function DataHealthPage() {
  return <DataHealth />;
}
