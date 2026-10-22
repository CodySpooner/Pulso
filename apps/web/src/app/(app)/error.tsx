"use client";

import { ErrorState } from "@/components/pulso/error-state";

export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="rounded-xl border border-border bg-card shadow-card">
      <ErrorState title="This page couldn’t load" error={error} retry={retry} />
    </div>
  );
}
