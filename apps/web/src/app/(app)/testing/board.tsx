"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { DndContext, DragOverlay, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, LayoutGroup } from "motion/react";
import * as m from "motion/react-m";
import { ArrowRightLeft, Clock, FlaskConical, OctagonAlert, Trophy } from "lucide-react";
import { DropdownMenu } from "radix-ui";

import { useApiReady } from "@/components/data-health/api";
import { Ago, Missing, PanelError, Pill, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, fetchClient } from "@/lib/api/client";
import { duration, ease, spring } from "@/lib/motion";
import { cn } from "@/lib/utils";

import { money } from "../products/[id]/profit/model";
import { KILL_REASONS, LIST, listKey, moveOptions, reasonOf, SIGNALS, spendBar, STAGES, stageLabel, staleMetrics, testDay, TRACK, type KillReason, type Move, type Stage, type Test } from "./model";
import { TestDrawer, Thumb } from "./test-drawer";

interface Note {
  text: string;
  tone: "done" | "error";
  undo?: () => void;
}

async function send({ id, stage, kill_reason }: Move) {
  const { data, error } = await fetchClient.PATCH("/v1/tests/{test_id}", { params: { path: { test_id: id } }, body: { stage, kill_reason } });
  if (!data) throw error;
  return data;
}

// WF-5b (DEC-315): five columns from GET /v1/tests. A card moves by its "Move to…" menu (keyboard and phone) or by
// pointer drag; Killed asks for a reason first. Moves are optimistic and roll back on error (model.ts).
export function TestingBoard() {
  const client = useQueryClient();
  const list = $api.useQuery("get", "/v1/tests", LIST, { enabled: useApiReady() });
  const mutation = useMutation(moveOptions(client, listKey, send));
  const [open, setOpen] = useState(Number(useSearchParams().get("test")) || null); // a Product Page link: /testing?test=12
  const [killing, setKilling] = useState<Test | null>(null);
  const [dragging, setDragging] = useState<Test | null>(null);
  const [dropped, setDropped] = useState<number | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const focusAfter = useRef<number | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const items = list.data?.items;

  useEffect(() => {
    if (!note) return;
    const timer = setTimeout(() => setNote(null), note.tone === "error" ? 10_000 : 6_000);
    return () => clearTimeout(timer);
  }, [note]);
  // A moved card remounts in its new column: focus follows it there.
  useEffect(() => {
    if (focusAfter.current == null) return;
    document.getElementById(`test-${focusAfter.current}`)?.focus();
    focusAfter.current = null;
  }, [items]);

  const move = (test: Test, stage: Stage, kill_reason?: KillReason, undoable = true) => {
    focusAfter.current = test.id;
    const after: Test = { ...test, stage, kill_reason: stage === "killed" ? (kill_reason ?? null) : null };
    mutation.mutateAsync({ id: test.id, stage, kill_reason }).then(
      () =>
        setNote({
          tone: "done",
          text: `Moved ${test.product_title} to ${stageLabel(stage)}.`,
          undo: undoable ? () => move(after, test.stage, test.kill_reason ?? undefined, false) : undefined,
        }),
      (error) => setNote({ tone: "error", text: `Couldn't move ${test.product_title} to ${stageLabel(stage)}: ${reasonOf(error)} It's back in ${stageLabel(test.stage)}.` }),
    );
  };
  const request = (test: Test, stage: Stage) => (stage === "killed" ? setKilling(test) : move(test, stage));

  if (!list.data)
    return list.isError ? (
      <section aria-label="Testing board" className="rounded-xl border border-border bg-card shadow-card">
        <PanelError title="Couldn't load your tests" headingLevel="h2" size="md" error={list.error} retry={() => void list.refetch()} />
      </section>
    ) : (
      <BoardSkeleton />
    );
  const { items: tests, kill_reasons, next_cursor } = list.data;
  const now = list.dataUpdatedAt;

  return (
    <div className="flex flex-col gap-4">
      {list.isRefetchError && <StaleLine boxed what="Couldn't refresh your tests" error={list.error} asOf={list.dataUpdatedAt} retry={() => void list.refetch()} />}
      {tests.length === 0 ? (
        <section aria-label="Testing board" className="rounded-xl border border-border bg-card shadow-card">
          <EmptyState
            icon={FlaskConical}
            headingLevel="h2"
            title="No tests yet. Start one from a product page"
            action={
              <Button asChild variant="secondary">
                <Link href="/discover">Find a product in Discover</Link>
              </Button>
            }
          >
            Open a product and press Start a test: it lands in Idea. From there you move it to Researching, Testing, and Winner or Killed.
          </EmptyState>
        </section>
      ) : (
        <DndContext
          sensors={sensors}
          onDragStart={({ active }) => setDragging(tests.find((t) => t.id === active.id) ?? null)}
          onDragCancel={() => setDragging(null)}
          onDragEnd={({ over }) => {
            setDragging(null);
            if (!dragging || !over || over.id === dragging.stage) return;
            setDropped(dragging.id); // it lands where it was let go, so it skips the layout animation
            request(dragging, over.id as Stage);
          }}
        >
          <LayoutGroup>
            <div className="grid items-start gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              {STAGES.map(({ value, label }) => {
                const cards = tests.filter((t) => t.stage === value);
                return (
                  <Column key={value} stage={value} label={label} count={cards.length} spend={value === "testing" ? cards.reduce((sum, t) => sum + t.ad_spend_minor, 0) : null} reasons={value === "killed" ? kill_reasons : null}>
                    {cards.map((test) => (
                      <Card
                        key={test.id}
                        test={test}
                        now={now}
                        layout={cards.length <= 50} // Motion's FLIP ceiling (vault Design/Motion System, rule 3)
                        instant={dropped === test.id}
                        hidden={dragging?.id === test.id}
                        onOpen={() => setOpen(test.id)}
                        onMove={(stage) => (setDropped(null), request(test, stage))}
                      />
                    ))}
                  </Column>
                );
              })}
            </div>
          </LayoutGroup>
          <DragOverlay dropAnimation={null}>{dragging && <div aria-hidden><CardBody test={dragging} now={now} className="scale-[1.02] shadow-popover" /></div>}</DragOverlay>
        </DndContext>
      )}
      {next_cursor != null && <p className="text-label text-subtle-foreground">Showing your newest 100 tests.</p>}
      <KillDialog
        test={killing}
        onClose={() => setKilling(null)}
        onKill={(reason) => {
          move(killing!, "killed", reason);
          setKilling(null);
        }}
      />
      <TestDrawer
        test={tests.find((t) => t.id === open)}
        onClose={() => {
          setOpen(null);
          if (window.location.search) window.history.replaceState(null, "", window.location.pathname); // a reload keeps it closed
        }}
      />
      <Toast note={note} />
    </div>
  );
}

function Column({ stage, label, count, spend, reasons, children }: { stage: Stage; label: string; count: number; spend: number | null; reasons: Partial<Record<KillReason, number>> | null; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  const id = `column-${stage}`;
  const why = Object.entries(reasons ?? {}).sort((a, b) => b[1] - a[1]) as [KillReason, number][];
  return (
    <section
      ref={setNodeRef}
      aria-labelledby={id}
      className={cn("flex min-w-0 flex-col rounded-xl border border-border-subtle bg-muted/60 transition-colors duration-(--duration-fast)", isOver && "border-brand/60 bg-brand-muted")}
    >
      <header className="flex flex-col gap-1.5 px-3 pt-3 pb-2">
        <h2 id={id} className="flex items-baseline justify-between gap-2 text-label font-semibold tracking-wide text-muted-foreground uppercase">
          {label}
          <span className="font-mono font-normal tabular-nums">
            <span className="sr-only">: </span>
            {count}
            <span className="sr-only">{count === 1 ? " test" : " tests"}</span>
          </span>
        </h2>
        {spend != null && spend > 0 && <p className="font-mono text-label text-subtle-foreground tabular-nums">{money(spend)} spent</p>}
        {why.length > 0 && (
          <ul aria-label="Kill reasons" className="flex flex-wrap gap-1">
            {why.map(([reason, n]) => (
              <li key={reason} className="inline-flex h-5.5 items-center gap-1 rounded-sm border border-border px-1.5 text-micro text-muted-foreground">
                {KILL_REASONS[reason].split(":")[0]}
                <span className="font-mono text-foreground tabular-nums">{n}</span>
              </li>
            ))}
          </ul>
        )}
      </header>
      <ul className="flex min-h-16 flex-col gap-2 px-2 pb-2">{count > 0 ? children : <li className="grid min-h-16 place-items-center rounded-lg border border-dashed border-border px-3 text-label text-subtle-foreground">No tests</li>}</ul>
    </section>
  );
}

function Card({ test, now, layout, instant, hidden, onOpen, onMove }: { test: Test; now: number; layout: boolean; instant: boolean; hidden: boolean; onOpen: () => void; onMove: (stage: Stage) => void }) {
  const { setNodeRef, listeners } = useDraggable({ id: test.id });
  return (
    // Moves settle with a shared layout animation across columns; a drop lands at once (vault Design/Motion System 7).
    <m.li ref={setNodeRef} {...listeners} layout={layout} layoutId={layout ? `test-${test.id}` : undefined} transition={{ layout: instant ? { duration: 0 } : spring.smooth }} className="touch-manipulation">
      <CardBody test={test} now={now} onOpen={onOpen} menu={<MoveMenu test={test} onMove={onMove} />} className={cn(hidden && "opacity-40")} />
    </m.li>
  );
}

function CardBody({ test, now, onOpen, menu, className }: { test: Test; now: number; onOpen?: () => void; menu?: React.ReactNode; className?: string }) {
  const stale = staleMetrics(test, now);
  return (
    <article aria-label={test.product_title} className={cn("@container relative flex flex-col gap-2.5 rounded-lg border border-border bg-card p-2.5 shadow-card hover:border-border-strong", className)}>
      <div className="flex items-start gap-2.5">
        <Thumb url={test.product_image_url} />
        <button
          id={onOpen && `test-${test.id}`}
          type="button"
          onClick={onOpen}
          // The whole card opens the drawer; its ring is drawn around the card.
          className="min-w-0 flex-1 text-left text-data font-medium text-foreground outline-none after:absolute after:inset-0 after:rounded-lg focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-ring"
        >
          <span className="line-clamp-2 break-words">{test.product_title}</span>
        </button>
        {menu}
      </div>
      {/* One stat a row in a narrow card (five columns), two a row from 15rem, so a value never meets a label. */}
      <dl className="grid gap-x-6 gap-y-1 text-label @min-[15rem]:grid-cols-2">
        <Stat label="Spend">{money(test.ad_spend_minor)}</Stat>
        <Stat label="Orders">{test.orders.toLocaleString("en-US")}</Stat>
        <Stat label="CPA">{test.cpa_minor == null ? <Missing reason="No source yet: no orders recorded" /> : money(test.cpa_minor)}</Stat>
        <Stat label="ROAS">{test.roas == null ? <Missing reason="No source yet: no ad spend recorded" /> : `${test.roas.toFixed(2)}×`}</Stat>
      </dl>
      {test.stage === "testing" && <StopLoss test={test} now={now} />}
      <p className="text-micro text-subtle-foreground">
        {stale ? (
          <Pill tone="warning" icon={Clock} className="h-auto min-h-5.5 py-0.5 whitespace-normal">
            <span>
              Metrics last updated <Ago iso={test.updated_at} now={now} source="Metrics you entered" />
            </span>
          </Pill>
        ) : (
          <>
            Metrics updated <Ago iso={test.updated_at} now={now} source="Metrics you entered" />
          </>
        )}
      </p>
    </article>
  );
}

/** A Testing card's day N, the API's stop-loss signal and spend against the stop-loss line (DEC-340). The chip
 *  recommends; the owner decides. Colour follows the signal only, and the chip always carries an icon and words. */
function StopLoss({ test, now }: { test: Test; now: number }) {
  const day = testDay(test, now);
  const bar = spendBar(test);
  const over = test.signal === "over_stop_loss";
  return (
    <div className="flex flex-col gap-1.5">
      {(day != null || test.signal) && (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-muted-foreground">
          {test.signal && (
            // The Pill shape (radius-sm tag) in the signal's tone; it fades in with 2 px of y, once.
            <m.span
              initial={{ opacity: 0, y: 2 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: duration.base, ease: ease.out }}
              className={cn("inline-flex h-5.5 items-center gap-1 rounded-sm px-1.5 font-medium whitespace-nowrap", over ? "bg-negative-muted text-negative" : "bg-positive-muted text-positive")}
            >
              {over ? <OctagonAlert className="size-3.5" aria-hidden /> : <Trophy className="size-3.5" aria-hidden />}
              {SIGNALS[test.signal]}
            </m.span>
          )}
          {day != null && <span className="font-mono tabular-nums">Day {day}</span>}
        </p>
      )}
      {test.signal_reason ? (
        <p className="text-micro text-subtle-foreground">{test.signal_reason}</p>
      ) : (
        bar && (
          <div className="flex flex-col gap-1">
            <p className="flex items-baseline justify-between gap-2 text-micro text-subtle-foreground">
              Stop-loss
              <span className="font-mono text-muted-foreground tabular-nums">{bar.line}</span>
            </p>
            <div aria-hidden className="relative h-1.5 rounded-full bg-border-subtle">
              <div className={cn("absolute inset-0 origin-left rounded-full", over ? "bg-negative" : "bg-muted-foreground")} style={{ transform: `scaleX(${bar.fill})` }} />
              <div className="absolute -inset-y-0.5 w-0.5 rounded-full bg-foreground" style={{ left: `${100 / TRACK}%` }} />
            </div>
          </div>
        )
      )}
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-subtle-foreground">{label}</dt>
      <dd className="num font-mono text-foreground">{children}</dd>
    </div>
  );
}

function MoveMenu({ test, onMove }: { test: Test; onMove: (stage: Stage) => void }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button size="icon-sm" variant="ghost" aria-label={`Move ${test.product_title} to…`} className="z-10 -mt-0.5 -mr-0.5">
          <ArrowRightLeft aria-hidden />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          className="z-50 min-w-44 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)"
        >
          <DropdownMenu.Label className="px-2 pt-1 pb-1.5 text-micro font-medium text-subtle-foreground uppercase">Move to</DropdownMenu.Label>
          {STAGES.filter((s) => s.value !== test.stage).map((s) => (
            <DropdownMenu.Item key={s.value} onSelect={() => onMove(s.value)} className="flex h-8 cursor-pointer items-center rounded-md px-2 text-data outline-none select-none pointer-coarse:h-(--hit-target) data-highlighted:bg-accent">
              {s.label}
              {s.value === "killed" && "…"}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function KillDialog({ test, onClose, onKill }: { test: Test | null; onClose: () => void; onKill: (reason: KillReason) => void }) {
  const killed = useRef(false);
  return (
    <Dialog open={test != null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        onOpenAutoFocus={() => (killed.current = false)}
        // After a kill, focus has followed the card to Killed; a cancel returns it to the card's menu.
        onCloseAutoFocus={(e) => killed.current && e.preventDefault()}
      >
        <DialogTitle>Why kill {test?.product_title}?</DialogTitle>
        <DialogDescription>A killed test needs a reason. The Killed column counts them, so you can see why tests fail.</DialogDescription>
        <div role="group" aria-label="Kill reason" className="-mx-2 grid gap-0.5">
          {(Object.entries(KILL_REASONS) as [KillReason, string][]).map(([reason, label]) => (
            <Button
              key={reason}
              variant="ghost"
              className="justify-start text-foreground"
              onClick={() => {
                killed.current = true;
                onKill(reason);
              }}
            >
              {label}
            </Button>
          ))}
        </div>
        <DialogClose asChild>
          <Button className="self-end">Cancel</Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}

/** A move's result, with Undo; polite, so it never takes focus (vault Design/UI States, Success / undo). */
function Toast({ note }: { note: Note | null }) {
  return (
    <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-4 bottom-20 z-40 flex justify-center lg:bottom-6">
      <AnimatePresence>
        {note && (
          <m.div
            key={note.text}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, transition: { duration: duration.fast } }}
            transition={{ duration: duration.slow, ease: ease.out }}
            className={cn("pointer-events-auto flex max-w-xl items-center gap-3 rounded-lg border bg-popover px-4 py-2.5 text-data text-popover-foreground shadow-dialog", note.tone === "error" ? "border-negative/40" : "border-border")}
          >
            <span>{note.text}</span>
            {note.undo && (
              <Button size="sm" variant="ghost" onClick={note.undo}>
                Undo
              </Button>
            )}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function BoardSkeleton() {
  return (
    <div role="status" aria-label="Loading your tests" className="grid items-start gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {STAGES.map(({ value }) => (
        <div key={value} className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-muted/60 p-2">
          <Skeleton className="m-1 h-4 w-24" />
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex flex-col gap-2.5 rounded-lg border border-border bg-card p-2.5">
              <div className="flex gap-2.5">
                <Skeleton className="size-9 rounded-md" />
                <Skeleton className="h-4 flex-1" />
              </div>
              <Skeleton className="h-8" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
