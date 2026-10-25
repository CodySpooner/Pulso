import type { Metadata } from "next";

import { PageHeader } from "@/components/pulso/page-header";

import { SettingsForm } from "./settings-form";

export const metadata: Metadata = { title: "Settings" };

// UX-10. The header renders on the server; the form reads and saves GET / PATCH /v1/settings on the client.
export default function SettingsPage() {
  return (
    <div className="flex w-full max-w-220 flex-col gap-5">
      <PageHeader title="Settings" description="The assumptions behind every landed margin. A change applies to the next margin Pulso computes." />
      <SettingsForm />
    </div>
  );
}
