"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BellOff, BellPlus, Pencil, SkipForward, Trash2, TriangleAlert } from "lucide-react";
import { DropdownMenu } from "radix-ui";

import { useAlertRules, useRuleWrites } from "@/components/alerts/api";
import { MUTES, mutedLabel, muteUntil, statusLine, targetOf, threshold, TYPES, type Rule } from "@/components/alerts/model";
import { RuleBuilder, useReturnFocus } from "@/components/alerts/rule-builder";
import { Ago, PanelError, StaleLine } from "@/components/data-health/atoms";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { isProblem } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { Action, AlertsInbox, EvaluationLine, Loading, Views } from "./inbox";

const box = "rounded-xl border border-border bg-card shadow-card";
const cell = "border-b border-border-subtle px-3 py-2 whitespace-nowrap max-md:border-0 max-md:p-0";
const menu =
  "z-50 min-w-48 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-popover data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-96 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 duration-(--duration-fast)";
const menuItem = "flex h-8 cursor-pointer items-center gap-2 rounded-md px-2 text-data outline-none select-none pointer-coarse:h-(--hit-target) data-highlighted:bg-accent";
const link = "relative hit-area rounded-sm font-medium text-foreground hover:underline";
const tones = { ok: "text-subtle-foreground", muted: "text-subtle-foreground", warning: "text-foreground" };
const COLUMNS = ["Rule", "Type", "Target", "Last fired", "Notifies"];
const noSubscribe = () => () => {};
const reason = (error: unknown) => (isProblem(error) ? error.detail : "The Pulso API didn’t answer. When it runs on your PC, this also means the PC is off.");

/** /alerts: the Inbox and Archived views (inbox.tsx), or Rules, by `?view=`. */
export function Alerts() {
  return useSearchParams().get("view") === "rules" ? <RulesTab /> : <AlertsInbox />;
}

// WF-4c (DEC-339): the workspace's rules, each with its last evaluation. Enabling and muting show at once and roll back
// if the API refuses; rules are made from a product (the Product Page's Create alert), so this tab edits them.
function RulesTab() {
  const hydrated = useSyncExternalStore(noSubscribe, () => true, () => false);
  const query = useAlertRules();
  const writes = useRuleWrites();
  const [edit, setEdit] = useState<{ rule: Rule; open: boolean } | null>(null);
  const [doomed, setDoomed] = useState<{ rule: Rule; open: boolean } | null>(null);
  const rules = query.data?.items;
  const now = query.dataUpdatedAt;
  const patch = (rule: Rule, body: { enabled?: boolean; muted_until?: string | null }) => writes.patch.mutate({ params: { path: { rule_id: rule.id } }, body });

  if (!hydrated) return <Loading />;
  return (
    <div className="flex flex-col gap-4">
      <Views current="rules" />
      {rules && rules.length > 0 && (
        <div className="text-label text-subtle-foreground">
          <EvaluationLine rules={rules} now={now} />
        </div>
      )}
      {writes.patch.isError && (
        <p role="alert" className="text-label text-foreground">
          <TriangleAlert className="mr-1 inline size-3.5 align-[-2px] text-negative" aria-hidden />
          <span className="font-medium text-negative">Couldn’t update the rule, so it’s back as it was.</span> {reason(writes.patch.error)}
        </p>
      )}
      {query.isRefetchError && <StaleLine boxed what="Couldn’t refresh rules" error={query.error} asOf={now} retry={() => void query.refetch()} />}
      {!rules ? (
        query.isError ? (
          <section className={box}>
            <PanelError headingLevel="h2" size="md" title="Couldn’t load your rules" error={query.error} retry={() => void query.refetch()} />
          </section>
        ) : (
          <Loading />
        )
      ) : rules.length === 0 ? (
        <section className={box}>
          <EmptyState
            icon={BellPlus}
            headingLevel="h2"
            title="No rules yet"
            action={
              <Button asChild>
                <Link href="/discover">Find a product in Discover</Link>
              </Button>
            }
          >
            Rules start from a product: open one and choose Create alert. A 5% supplier price change is filled in, so it takes one more click.
            Products you test get supplier cost, freight and stock-out rules on their own.
          </EmptyState>
        </section>
      ) : (
        <>
          <div
            role="region"
            aria-label="Alert rules"
            tabIndex={0}
            className={cn(box, "max-h-[max(24rem,calc(100dvh-20rem))] overflow-auto overscroll-contain max-md:max-h-none max-md:overflow-visible max-md:border-0 max-md:bg-transparent max-md:shadow-none")}
          >
            <table className="w-full border-separate border-spacing-0 zone-data max-md:block">
              <thead className="sticky top-0 z-20 bg-card max-md:hidden">
                <tr className="row-h text-label text-muted-foreground">
                  {COLUMNS.map((name) => (
                    <th key={name} scope="col" className={cn(cell, "border-border bg-card font-medium", name === "Last fired" ? "num" : "text-left")}>
                      {name}
                    </th>
                  ))}
                  <th scope="col" className={cn(cell, "border-border bg-card")}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="max-md:flex max-md:flex-col max-md:gap-2">
                {rules.map((rule) => (
                  <Row
                    key={rule.id}
                    rule={rule}
                    now={now}
                    onEnabled={(enabled) => patch(rule, { enabled })}
                    onMute={(hours) => patch(rule, { muted_until: hours === false ? null : muteUntil(hours, Date.now()) })}
                    onEdit={() => setEdit({ rule, open: true })}
                    onDelete={() => setDoomed({ rule, open: true })}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-label text-subtle-foreground">
            {rules.length} {rules.length === 1 ? "rule" : "rules"}, newest first{query.data?.next_cursor && " (the newest 100)"} · as of{" "}
            <time dateTime={new Date(now).toISOString()}>{formatUtc(new Date(now).toISOString())}</time>
          </p>
        </>
      )}
      {edit && <RuleBuilder rule={edit.rule} open={edit.open} onOpenChange={(open) => setEdit({ ...edit, open })} />}
      {doomed && <DeleteDialog rule={doomed.rule} open={doomed.open} onOpenChange={(open) => setDoomed({ ...doomed, open })} />}
    </div>
  );
}

// Rows never animate (Motion System); the switch's thumb slides on its own.
function Row({
  rule,
  now,
  onEnabled,
  onMute,
  onEdit,
  onDelete,
}: {
  rule: Rule;
  now: number;
  onEnabled: (on: boolean) => void;
  onMute: (hours: number | null | false) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const type = TYPES[rule.type];
  const target = targetOf(rule);
  const status = statusLine(rule, now);
  const muted = mutedLabel(rule.muted_until, now);
  const limit = threshold(rule);
  const testing = rule.target_type === "test";
  return (
    <tr className="hover:bg-(--table-row-hover) max-md:grid max-md:grid-cols-[minmax(0,1fr)_auto_auto] max-md:items-center max-md:gap-x-2 max-md:gap-y-1 max-md:rounded-lg max-md:border max-md:border-border max-md:bg-card max-md:p-3">
      <th scope="row" className={cn(cell, "max-w-78 text-left font-normal max-md:col-span-3 max-md:max-w-none")}>
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium text-foreground">{rule.name}</span>
          {testing && (
            <span title="A Testing default: rename it, change its %, turn it off or mute it. It can’t be deleted." className="shrink-0 rounded-sm border border-border-subtle px-1.5 text-label text-muted-foreground">
              Default
            </span>
          )}
        </span>
        <span className={cn("mt-0.5 flex items-center gap-1 text-label", tones[status.tone])}>
          {status.tone === "warning" && <SkipForward className="size-3.5 shrink-0 text-warning" aria-hidden />}
          <span className="truncate" title={rule.last_evaluated_at ? `${status.text} · last evaluated ${formatUtc(rule.last_evaluated_at)}` : status.text}>
            {status.text}
          </span>
        </span>
        {muted && rule.enabled && <span className="mt-0.5 block text-label text-foreground md:hidden">{muted}</span>}
      </th>
      <td className={cn(cell, "text-muted-foreground max-md:col-span-3")}>
        <span className="flex items-center gap-1.5">
          {type && <type.icon className="size-4 shrink-0" strokeWidth={1.5} aria-hidden />}
          {type?.label ?? rule.type}
          {limit && <span className="text-foreground tabular-nums">{limit}</span>}
        </span>
      </td>
      <td className={cn(cell, "max-w-64 truncate max-md:col-span-3 max-md:max-w-none")}>
        {target.href ? (
          <Link href={target.href} className={link}>
            {target.label}
          </Link>
        ) : (
          <span className="text-foreground">{target.label}</span>
        )}
        <span className="text-muted-foreground"> · {target.detail}</span>
      </td>
      <td className={cn(cell, "num text-muted-foreground max-md:text-left max-md:text-label")}>
        <span className="md:hidden">Last fired </span>
        {rule.last_fired_at ? <Ago iso={rule.last_fired_at} now={now} source={rule.name} /> : "never"}
      </td>
      <td className={cell}>
        <span className="flex items-center gap-2">
          <Switch checked={rule.enabled} onCheckedChange={onEnabled} aria-label={`Notify: ${rule.name}`} />
          <span className={cn("text-label max-md:sr-only", muted && rule.enabled ? "text-foreground" : "text-muted-foreground")}>
            {!rule.enabled ? "Off" : (muted ?? "On")}
          </span>
        </span>
      </td>
      <td className={cn(cell, "w-28 max-md:w-auto")}>
        <span className="flex justify-end gap-1">
          <DropdownMenu.Root>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenu.Trigger asChild>
                  <Button size="icon-sm" variant="ghost" aria-label={`Mute: ${rule.name}`}>
                    <BellOff aria-hidden />
                  </Button>
                </DropdownMenu.Trigger>
              </TooltipTrigger>
              <TooltipContent>Mute</TooltipContent>
            </Tooltip>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={4} className={menu}>
                {MUTES.map(([label, hours]) => (
                  <DropdownMenu.Item key={label} className={menuItem} onSelect={() => onMute(hours)}>
                    {hours === null ? label : `For ${label}`}
                  </DropdownMenu.Item>
                ))}
                {rule.muted_until && (
                  <DropdownMenu.Item className={menuItem} onSelect={() => onMute(false)}>
                    Unmute
                  </DropdownMenu.Item>
                )}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
          <Action hint="Edit" name={rule.name} icon={Pencil} onClick={onEdit} />
          {!testing && <Action hint="Delete" name={rule.name} icon={Trash2} onClick={onDelete} />}
        </span>
      </td>
    </tr>
  );
}

function DeleteDialog({ rule, open, onOpenChange }: { rule: Rule; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { remove } = useRuleWrites();
  return (
    <Dialog open={open} onOpenChange={(next) => (onOpenChange(next), remove.reset())}>
      <DialogContent {...useReturnFocus()}>
        <DialogTitle>Delete {rule.name}?</DialogTitle>
        <DialogDescription>It stops watching now. The alerts it already fired stay in your inbox. This can’t be undone.</DialogDescription>
        {remove.isError && (
          <p role="alert" className="text-label text-negative">
            {reason(remove.error)}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button
            variant="destructive"
            aria-disabled={remove.isPending}
            onClick={() => !remove.isPending && remove.mutate({ params: { path: { rule_id: rule.id } } }, { onSuccess: () => onOpenChange(false) })}
          >
            Delete rule
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
