// Pure helpers for the Testing Board (WF-5b, DEC-315): the columns, the kill reasons in words, an optimistic move
// and its rollback, and the start snapshot's break-even. CPA and ROAS come from the API (DEC-312); no profit maths here.

import type { QueryClient, QueryKey, UseMutationOptions } from "@tanstack/react-query";

import { $api, isProblem } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import type { Calc } from "../products/[id]/profit/model";

export type Test = components["schemas"]["ProductTestOut"];
export type Page = components["schemas"]["ProductTestPage"];
export type Stage = Test["stage"];
export type KillReason = NonNullable<Test["kill_reason"]>;
export interface Move {
  id: number;
  stage: Stage;
  kill_reason?: KillReason;
}

// ponytail: the newest 100 tests (the API's largest page); page the board once a workspace has more.
export const LIST = { params: { query: { limit: 100 } } };
export const listKey = $api.queryOptions("get", "/v1/tests", LIST).queryKey;
export const reasonOf = (error: unknown) => (isProblem(error) ? error.detail : "The Pulso API didn't answer. Check that it is running, then try again.");

export const STAGES: { value: Stage; label: string }[] = [
  { value: "idea", label: "Idea" },
  { value: "researching", label: "Researching" },
  { value: "testing", label: "Testing" },
  { value: "winner", label: "Winner" },
  { value: "killed", label: "Killed" },
];
export const stageLabel = (stage: Stage) => STAGES.find((s) => s.value === stage)!.label;

export const KILL_REASONS: Record<KillReason, string> = {
  no_sales_over_stop_loss: "No sales over stop-loss",
  cpa_above_break_even: "CPA above break-even",
  low_ctr_creatives: "Low CTR on creatives",
  supplier_issue: "Supplier issue: stock, quality or shipping",
  sample_quality: "Sample quality",
  margin_too_thin: "Margin too thin",
  saturated: "Saturated market",
  ad_account_rejection: "Ad account rejection",
  other: "Other: say why in notes",
};

/** The page as the API will answer the move: the stage, the kill reason (Killed only) and the R-24 counts, which
 *  omit a reason with no killed test. */
export function moved(page: Page, { id, stage, kill_reason }: Move): Page {
  const test = page.items.find((t) => t.id === id);
  if (!test) return page;
  const reason = stage === "killed" ? (kill_reason ?? null) : null;
  const counts = { ...page.kill_reasons };
  if (test.kill_reason && !--counts[test.kill_reason]!) delete counts[test.kill_reason];
  if (reason) counts[reason] = (counts[reason] ?? 0) + 1;
  return { ...page, kill_reasons: counts, items: page.items.map((t) => (t.id === id ? { ...t, stage, kill_reason: reason } : t)) };
}

/** useMutation options for a move: the card moves before the API answers, and a failure moves back that card only,
 *  so a second move made meanwhile stays. The list refetches either way, for the dates and the start snapshot. */
export function moveOptions(client: QueryClient, key: QueryKey, send: (move: Move) => Promise<Test>): UseMutationOptions<Test, unknown, Move, Move | undefined> {
  const update = (move: Move) => client.setQueryData<Page>(key, (page) => page && moved(page, move));
  return {
    mutationFn: send,
    onMutate: async (move) => {
      await client.cancelQueries({ queryKey: key });
      const was = client.getQueryData<Page>(key)?.items.find((t) => t.id === move.id);
      update(move);
      return was && { id: was.id, stage: was.stage, kill_reason: was.kill_reason ?? undefined };
    },
    onError: (_error, _move, back) => void (back && update(back)),
    onSettled: () => client.invalidateQueries({ queryKey: key }),
  };
}

type Snapshot = Pick<Calc, "complete" | "price_minor" | "landed_cost_minor" | "margin_minor"> & { captured_at: string };

/** The economics the test started with (R-21): null before it enters Testing, "incomplete" when the Profit calc
 *  lacked a price or a supplier. Break-even CPA is the margin before ads; break-even ROAS is price over it. */
export function breakEven(test: Test) {
  const s = test.start_snapshot as Snapshot | null;
  if (!s) return null;
  if (!s.complete || s.margin_minor == null || s.price_minor == null || s.landed_cost_minor == null) return "incomplete";
  return { price: s.price_minor, landed: s.landed_cost_minor, cpa: s.margin_minor, roas: s.margin_minor > 0 ? s.price_minor / s.margin_minor : null, capturedAt: s.captured_at };
}

/** A Testing card whose metrics are over 48 h old (vault Features/Testing Board, States). */
export const staleMetrics = (test: Test, now: number) => test.stage === "testing" && now - Date.parse(test.updated_at) > 48 * 3_600_000;
