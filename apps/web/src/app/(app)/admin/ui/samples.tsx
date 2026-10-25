"use client";

import { useState } from "react";
import { LayoutGroup } from "motion/react";
import * as m from "motion/react-m";
import { RotateCcw } from "lucide-react";

import { ErrorState } from "@/components/pulso/error-state";
import { LogoMark } from "@/components/pulso/logo";
import { Button } from "@/components/ui/button";
import { duration, ease, spring, stagger } from "@/lib/motion";

// A specimen error id, so the gallery shows the full anatomy: Retry, Copy error ID and the id in mono.
const specimenError = Object.assign(new Error("Specimen"), { digest: "2950841734" });

/** Inline ErrorState specimen. Retry has nothing to reload in the gallery. */
export function ErrorSample() {
  return <ErrorState variant="inline" title="Couldn’t load suppliers" error={specimenError} retry={() => {}} />;
}

const durations = [
  { name: "fast", seconds: duration.fast },
  { name: "base", seconds: duration.base },
  { name: "slow", seconds: duration.slow },
];
const ranges = ["Day", "Week", "Month"] as const;

function Sample({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <figure className="flex flex-col gap-3 rounded-lg border border-border-subtle p-4">
      <div className="grid min-h-24 place-items-center">{children}</div>
      <figcaption className="flex flex-col gap-0.5">
        <span className="text-data font-medium text-foreground">{title}</span>
        <span className="text-label text-subtle-foreground">{note}</span>
      </figcaption>
    </figure>
  );
}

// The Phase 0 motion vocabulary (vault Design/Motion System). Nothing moves on first paint; Replay remounts
// the samples so their enter animations run again. MotionConfig reducedMotion="user" drops the movement and
// keeps the fades; the logo draw turns instant.
export function MotionSamples() {
  const [run, setRun] = useState(0);
  const [range, setRange] = useState<(typeof ranges)[number]>("Week");
  const from = <T extends object>(initial: T) => (run ? initial : false);
  const enter = { duration: duration.base, ease: ease.out };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button onClick={() => setRun((r) => r + 1)}>
          <RotateCcw aria-hidden />
          Replay motion
        </Button>
        <p className="text-data text-muted-foreground">
          <span className="motion-reduce:hidden">Motion is on. Turn on reduced motion in your OS to check the fallback.</span>
          <span className="hidden motion-reduce:inline">Reduced motion is on: movement is dropped and fades stay.</span>
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Sample title="Duration tokens" note="fast 120 · base 200 · slow 280 ms, ease-out on enter">
          <ul className="flex w-full flex-col gap-3">
            {durations.map((d) => (
              <li key={d.name} className="flex items-center gap-3">
                <span className="w-10 font-mono text-label text-muted-foreground">{d.name}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-border-subtle">
                  <m.span
                    key={run}
                    className="block h-full origin-left rounded-full bg-brand"
                    initial={from({ scaleX: 0 })}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: d.seconds, ease: ease.out }}
                  />
                </span>
              </li>
            ))}
          </ul>
        </Sample>

        <Sample title="Route enter" note="Opacity 0→1 and y 4→0 at base, enter only">
          <m.div key={run} className="flex w-full flex-col gap-2" initial={from({ opacity: 0, y: 4 })} animate={{ opacity: 1, y: 0 }} transition={enter}>
            <span className="h-3 w-1/3 rounded-sm bg-border-strong" />
            <span className="h-2 w-3/4 rounded-sm bg-border" />
            <span className="h-2 w-2/3 rounded-sm bg-border" />
          </m.div>
        </Sample>

        <Sample title="Card stagger" note="40 ms apart, first 6 only, y 8→0">
          <div key={run} className="grid w-full grid-cols-4 gap-2">
            {[0, 1, 2, 3].map((i) => (
              <m.span
                key={i}
                className="h-12 rounded-lg border border-border bg-background"
                initial={from({ opacity: 0, y: 8 })}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...enter, delay: Math.min(i, stagger.max) * stagger.step }}
              />
            ))}
          </div>
        </Sample>

        <Sample title="Shared indicator" note="One pill slides between options (snappy spring)">
          <LayoutGroup id="gallery-range">
            <div role="group" aria-label="Range" className="inline-flex rounded-md border border-border bg-secondary p-0.5">
              {ranges.map((r) => (
                <button
                  key={r}
                  type="button"
                  aria-pressed={range === r}
                  onClick={() => setRange(r)}
                  className="relative hit-area h-7 rounded-sm px-3 text-label font-medium text-muted-foreground transition-colors duration-(--duration-fast) ease-standard hover:text-foreground aria-pressed:text-foreground"
                >
                  {range === r && <m.span layoutId="range-pill" transition={spring.snappy} className="absolute inset-0 rounded-sm segment-thumb" />}
                  <span className="relative">{r}</span>
                </button>
              ))}
            </div>
          </LayoutGroup>
        </Sample>

        <Sample title="Dialog panel" note="Scale 0.98→1 with a fade at base, like Ctrl+K">
          <m.div
            key={run}
            className="flex w-full flex-col gap-1 rounded-lg border border-border bg-popover p-1.5 shadow-popover"
            initial={from({ opacity: 0, scale: 0.98, y: -8 })}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={enter}
          >
            <span className="flex h-6 items-center rounded-sm bg-accent px-2">
              <span className="h-2 w-1/2 rounded-sm bg-border-strong" />
            </span>
            <span className="flex h-6 items-center px-2">
              <span className="h-2 w-1/3 rounded-sm bg-border" />
            </span>
          </m.div>
        </Sample>

        <Sample title="Logo draw" note="Draws once on sign-in and the first-run dashboard">
          <LogoMark key={run} draw={run > 0} className="size-10 text-brand" />
        </Sample>
      </div>
    </div>
  );
}
