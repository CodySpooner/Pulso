"use client";

import { ErrorState } from "@/components/pulso/error-state";

export default function DailyPulseError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="rounded-xl border border-border bg-card shadow-card">
      <ErrorState title="Couldn’t load the Daily Pulse" error={error} retry={retry} />
    </div>
  );
}
