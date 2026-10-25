"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, CircleDashed, Lock, TriangleAlert } from "lucide-react";

import { useApiReady } from "@/components/data-health/api";
import { PanelError, StaleLine } from "@/components/data-health/atoms";
import { CopyButton, SelectableId } from "@/components/pulso/copy-button";
import { useModKey } from "@/components/pulso/mod-key";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { formatUtc } from "@/lib/format";
import { cn } from "@/lib/utils";

import { apiFieldErrors, errors, FIELDS, isDirty, toBody, toDraft, type Draft, type Field, type Settings } from "./model";

const LABELS: Record<Field, string> = {
  payment_fee_bps: "Processing rate",
  payment_fee_fixed_minor: "Fixed fee per order",
  shopify_fee_bps: "Shopify transaction fee",
  default_cpa_minor: "Ad cost per order (CPA)",
  target_margin_bps: "Target margin",
  duty_default_bps: "Default duty rate",
  customs_fee_minor: "Import fee per order",
  returns_bps: "Return rate",
};
const inputId = (key: Field) => `setting-${key}`;
const focusField = (key: Field) => requestAnimationFrame(() => document.getElementById(inputId(key))?.focus());

// UX-10 (DEC-251): one form, one Save. The owner types percent and dollars; the API stores basis points and cents.
// Unsaved input survives a failed save and a background refetch; only Reset or a successful save replaces it.
export function SettingsForm() {
  const queryClient = useQueryClient();
  const query = $api.useQuery("get", "/v1/settings", {}, { enabled: useApiReady() });
  const { queryKey } = $api.queryOptions("get", "/v1/settings", {});
  const patch = $api.useMutation("patch", "/v1/settings");
  const [synced, setSynced] = useState<Settings>();
  const [draft, setDraft] = useState<Draft>();
  const [touched, setTouched] = useState<ReadonlySet<Field>>(new Set());
  const [serverErrors, setServerErrors] = useState<Partial<Record<Field, string>>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const [attempted, setAttempted] = useState(false);
  const [saved, setSaved] = useState(false);
  const mod = useModKey();

  // New server data replaces the form only while it holds no unsaved change (React's adjust-state-during-render).
  if (query.data && query.data !== synced && (!draft || !synced || !isDirty(draft, synced))) {
    setSynced(query.data);
    // A withheld margin's "Set duty" (the product Overview, imp-368) arrives at #duty: the first draft opens the rate.
    const forDuty = !draft && window.location.hash === "#duty";
    setDraft(forDuty ? { ...toDraft(query.data), dutySet: true } : toDraft(query.data));
  }

  const dirty = !!draft && !!synced && isDirty(draft, synced);
  const invalid = draft ? errors(draft) : {};
  const blocking = FIELDS.filter((key) => invalid[key]);
  const shown = (key: Field) => (touched.has(key) ? invalid[key] : undefined) ?? serverErrors[key];

  const save = () => {
    if (!draft || !dirty || patch.isPending) return;
    const body = toBody(draft);
    if (!body) {
      setAttempted(true);
      setTouched(new Set(FIELDS));
      focusField(blocking[0]);
      return;
    }
    setAttempted(false);
    setFailure(null);
    setServerErrors({});
    setSaved(false);
    const sent = draft;
    patch.mutate(
      { body },
      {
        onSuccess: (data) => {
          queryClient.setQueryData(queryKey, data);
          setSynced(data);
          setDraft((current) => (current === sent ? toDraft(data) : current)); // never drop an edit made mid-save
          setTouched(new Set());
          setSaved(true);
        },
        onError: (error) => {
          setFailure(error);
          if (isProblem(error)) setServerErrors(apiFieldErrors(error.errors));
        },
      },
    );
  };

  const reset = () => {
    if (!synced || !dirty) return;
    setDraft(toDraft(synced));
    setTouched(new Set());
    setServerErrors({});
    setFailure(null);
    setAttempted(false);
  };

  const edit = (change: Partial<Draft["values"]>, dutySet?: boolean) => {
    setDraft((d) => d && { values: { ...d.values, ...change }, dutySet: dutySet ?? d.dutySet });
    setSaved(false);
    setServerErrors((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !(key in change))));
  };

  // Ctrl/⌘+S saves from anywhere on the page, inside a field too, and never opens the browser's Save page dialog.
  const onKeyDown = useEffectEvent((e: KeyboardEvent) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey || e.key.toLowerCase() !== "s") return;
    e.preventDefault();
    save();
  });
  useEffect(() => {
    const listener = (e: KeyboardEvent) => onKeyDown(e);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  // Closing or reloading the tab with unsaved changes asks first.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Arriving at #duty, the first draft opened the rate (above); it takes focus once, as the Set duty check gives it.
  const loaded = !!draft;
  useEffect(() => {
    if (loaded && window.location.hash === "#duty") document.getElementById(inputId("duty_default_bps"))?.focus();
  }, [loaded]);

  if (!draft || !synced) {
    return query.isError ? (
      <section aria-label="Settings" className="rounded-xl border border-border bg-card shadow-card">
        <PanelError title="Couldn't load your settings" headingLevel="h2" size="md" error={query.error} retry={() => void query.refetch()} />
      </section>
    ) : (
      <FormSkeleton />
    );
  }

  const field = (key: Field, unit: "%" | "$", hint: React.ReactNode, className?: string) => (
    <NumberField
      field={key}
      unit={unit}
      hint={hint}
      value={draft.values[key]}
      error={shown(key)}
      onChange={(value) => edit({ [key]: value })}
      onBlur={() => setTouched((t) => (t.has(key) ? t : new Set(t).add(key)))}
      className={className}
    />
  );

  const checks = [
    synced.duty_default_bps === null && {
      id: "duty",
      text: "Duty isn't set, so landed margins stay incomplete.",
      action: "Set duty",
      go: () => {
        edit({}, true);
        focusField("duty_default_bps");
      },
    },
    synced.payment_fee_bps === 0 &&
      synced.payment_fee_fixed_minor === 0 && {
        id: "fees",
        text: "Payment processing is 0%, so margins count no processor fee.",
        action: "Set fees",
        go: () => focusField("payment_fee_bps"),
      },
  ].filter((check) => check !== false);

  return (
    <form
      noValidate
      aria-label="Workspace settings"
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      {query.isError && (
        <StaleLine boxed what="Couldn't refresh your settings" error={query.error} asOf={query.dataUpdatedAt} retry={() => void query.refetch()} />
      )}
      {checks.length > 0 && (
        <section aria-labelledby="checks-title" className="rounded-xl border border-dashed border-border-strong bg-card px-4 py-3">
          <h2 id="checks-title" className="text-data font-medium text-foreground">
            {checks.length === 1 ? "1 assumption to check" : `${checks.length} assumptions to check`}
          </h2>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {checks.map((check) => (
              <li key={check.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-data text-muted-foreground">
                <CircleDashed className="size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
                <span className="min-w-0 flex-1">{check.text}</span>
                <Button type="button" size="sm" variant="link" onClick={check.go}>
                  {check.action}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Section id="market" title="Market" description="Pulso v1 covers the US market in US dollars.">
        <dl className="grid gap-4 sm:grid-cols-2">
          {[
            ["Country", "United States", "US"],
            ["Currency", "US dollar", "USD"],
          ].map(([term, name, code]) => (
            <div key={term} className="flex min-w-0 flex-col gap-1.5">
              <dt className="text-data font-medium text-foreground">{term}</dt>
              <dd className="flex h-(--input-h) items-center gap-2 rounded-md border border-dashed border-border-strong px-2.5 text-data text-muted-foreground">
                <Lock className="size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
                <span className="truncate">{name}</span>
                <span className="ml-auto font-mono text-label text-subtle-foreground">{code}</span>
                <span className="sr-only">, locked</span>
              </dd>
            </div>
          ))}
        </dl>
        <p className="text-label text-subtle-foreground">Locked for v1. Other markets and currencies arrive with multi-country support.</p>
      </Section>

      <Section id="fees" title="Fees" description="What each sale costs. Pulso takes these off the retail price.">
        <div className="grid grid-cols-2 items-start gap-4 sm:flex">
          {field("payment_fee_bps", "%", "Of the order total.", "sm:w-44")}
          {field("payment_fee_fixed_minor", "$", "On every order.", "sm:w-44")}
        </div>
        {field("shopify_fee_bps", "%", "Only with a gateway other than Shopify Payments. 0% otherwise.")}
        {field("default_cpa_minor", "$", "What one sale costs in ads. The Profit tab uses it for margin after ads.")}
      </Section>

      <Section id="target" title="Targets" description="What a product has to clear to be worth testing.">
        {field("target_margin_bps", "%", "Margin per order after ad cost. Margins are compared with it as they arrive in Discover and the Profit tab.")}
      </Section>

      <Section id="duty" title="Duty default" description="US import duty on the goods. With no de minimis exemption, imported orders pay it.">
        <fieldset className="flex min-w-0 flex-col gap-1.5">
          <legend className="mb-1.5 text-data font-medium text-foreground">Duty</legend>
          <div className="inline-flex h-(--input-h) w-fit rounded-md border border-border bg-secondary p-0.5">
            {[false, true].map((set) => (
              <label
                key={String(set)}
                className="relative hit-area flex h-full cursor-pointer items-center rounded-sm px-3 text-label font-medium text-muted-foreground transition-colors duration-(--duration-fast) select-none hover:text-foreground has-checked:text-foreground has-checked:segment-thumb has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring"
              >
                <input type="radio" name="duty-set" className="sr-only" checked={draft.dutySet === set} onChange={() => edit({}, set)} />
                {set ? "Set a rate" : "Not set"}
              </label>
            ))}
          </div>
        </fieldset>
        {draft.dutySet ? (
          field("duty_default_bps", "%", "On the goods value. 0% is a rate: margins then count no duty. Rates can pass 100%.")
        ) : (
          <p className="flex gap-2 rounded-lg border border-dashed border-border-strong px-3 py-2.5 text-data text-muted-foreground">
            <CircleDashed className="mt-0.5 size-3.5 shrink-0 text-subtle-foreground" aria-hidden />
            <span>
              <span className="font-medium text-foreground">Duty not set.</span> Landed margins that need it stay incomplete and read “duty not set”
              until you set a rate, or the supplier&apos;s quote is DDP (duties paid).
            </span>
          </p>
        )}
        {field("customs_fee_minor", "$", "Clearance or brokerage your carrier passes on. DDP quotes skip it.")}
      </Section>

      <Section id="returns" title="Returns" description="What returns cost you. Goods and freight aren't recovered.">
        {field("returns_bps", "%", "Share of revenue you give back on returns.")}
      </Section>

      <div className="sticky bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-10 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-border bg-popover px-4 py-3 shadow-popover md:bottom-4">
        <div className="min-w-0 flex-[1_1_14rem] text-data">
          <SaveStatus
            pending={patch.isPending}
            failure={failure}
            blocking={attempted ? blocking.map((key) => LABELS[key]) : []}
            dirty={dirty}
            saved={saved}
            asOf={query.dataUpdatedAt}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span aria-hidden className="flex items-center gap-1 text-micro text-subtle-foreground pointer-coarse:hidden">
            <Kbd>{mod}</Kbd>
            <Kbd>S</Kbd>
          </span>
          {/* aria-disabled, not disabled, so focus stays put when a save or reset makes the form clean. */}
          <Button type="button" variant="ghost" aria-disabled={!dirty} onClick={reset}>
            Reset
          </Button>
          <Button type="submit" variant="primary" aria-disabled={!dirty || patch.isPending}>
            {patch.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>
    </form>
  );
}

function SaveStatus({
  pending,
  failure,
  blocking,
  dirty,
  saved,
  asOf,
}: {
  pending: boolean;
  failure: unknown;
  blocking: string[];
  dirty: boolean;
  saved: boolean;
  asOf: number;
}) {
  const stamp = <time dateTime={new Date(asOf).toISOString()}>{formatUtc(new Date(asOf).toISOString())}</time>;
  if (failure != null && !pending) {
    const problem = isProblem(failure) ? failure : null;
    return (
      <div role="alert" className="flex flex-col gap-1">
        <p className="text-foreground">
          <TriangleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-negative" aria-hidden />
          <span className="font-medium">Couldn&apos;t save. Your changes are still here.</span>{" "}
          {problem ? problem.detail : "The Pulso API didn't answer."}
        </p>
        {problem && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="min-w-0 font-mono text-label text-muted-foreground">
              Error ID <SelectableId value={problem.request_id} label="Error ID" className="inline-block max-w-full break-all" />
            </p>
            <CopyButton value={problem.request_id} label="Copy error ID" />
          </div>
        )}
      </div>
    );
  }
  if (blocking.length > 0) {
    return (
      <p role="alert" className="text-foreground">
        <CircleAlert className="mr-1.5 inline size-3.5 align-[-2px] text-negative" aria-hidden />
        <span className="font-medium">{blocking.length === 1 ? "Fix 1 field to save:" : `Fix ${blocking.length} fields to save:`}</span> {blocking.join(", ")}.
      </p>
    );
  }
  return (
    <p role="status" className="text-muted-foreground">
      {pending ? (
        "Saving…"
      ) : dirty ? (
        <span className="font-medium text-foreground">Unsaved changes</span>
      ) : saved ? (
        <>
          <CircleCheck className="mr-1.5 inline size-3.5 align-[-2px] text-positive" aria-hidden />
          <span className="font-medium text-foreground">Saved.</span> The next margin uses these · as of {stamp}
        </>
      ) : (
        <>Your workspace&apos;s settings · as of {stamp}</>
      )}
    </p>
  );
}

function Section({ id, title, description, children }: { id: string; title: string; description: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-18 rounded-xl border border-border bg-card shadow-card lg:scroll-mt-4">
      <div className="grid gap-x-8 gap-y-4 p-4 sm:p-5 md:grid-cols-[13rem_minmax(0,1fr)] md:p-6">
        <div className="flex flex-col gap-1">
          <h2 id={`${id}-title`} className="text-title-3 font-semibold text-foreground">
            {title}
          </h2>
          <p className="text-data text-muted-foreground">{description}</p>
        </div>
        <div className="flex min-w-0 flex-col gap-5">{children}</div>
      </div>
    </section>
  );
}

function NumberField({
  field,
  unit,
  hint,
  value,
  error,
  onChange,
  onBlur,
  className,
}: {
  field: Field;
  unit: "%" | "$";
  hint: React.ReactNode;
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
  onBlur: () => void;
  className?: string;
}) {
  const id = inputId(field);
  const note = error ? `${id}-error` : `${id}-hint`;
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-data font-medium text-foreground">
        {LABELS[field]}
        <span className="sr-only">, {unit === "%" ? "percent" : "US dollars"}</span>
      </label>
      <div
        className={cn(
          "flex h-(--input-h) w-full max-w-44 items-center rounded-md border bg-secondary text-data transition-colors duration-(--duration-fast) has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring",
          error ? "border-negative" : "border-border hover:border-border-strong",
        )}
      >
        {unit === "$" && (
          <span aria-hidden className="pl-2.5 text-subtle-foreground">
            $
          </span>
        )}
        <input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={note}
          className="h-full min-w-0 flex-1 bg-transparent px-2.5 text-right text-foreground tabular-nums outline-none placeholder:text-subtle-foreground"
        />
        {unit === "%" && (
          <span aria-hidden className="pr-2.5 text-subtle-foreground">
            %
          </span>
        )}
      </div>
      {error ? (
        <p id={note} className="flex gap-1 text-label text-negative">
          <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
          {error}
        </p>
      ) : (
        <p id={note} className="text-label text-subtle-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

/** The loading form, at its final layout: section cards with a label and a field box per row. */
function FormSkeleton() {
  return (
    <div aria-busy className="flex flex-col gap-6">
      <span className="sr-only" role="status">
        Loading your settings…
      </span>
      {[2, 3, 1, 2].map((rows, i) => (
        <div key={i} className="grid gap-x-8 gap-y-4 rounded-xl border border-border bg-card p-4 shadow-card sm:p-5 md:grid-cols-[13rem_minmax(0,1fr)] md:p-6">
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3.5 w-40" />
          </div>
          <div className="flex flex-col gap-5">
            {Array.from({ length: rows }, (_, j) => (
              <div key={j} className="flex flex-col gap-1.5">
                <Skeleton className="h-3.5 w-28" />
                <Skeleton className="h-(--input-h) w-44 rounded-md" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
