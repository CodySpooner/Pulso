"use client";

import { LogoMark } from "@/components/pulso/logo";
import { useOncePerSession } from "@/lib/navigation";

// The first-run mark draws once per session, on a client navigation (Motion System pattern 18).
export function FirstRunMark() {
  return <LogoMark draw={useOncePerSession("pulso:logo-draw")} className="relative size-9 text-brand" />;
}
