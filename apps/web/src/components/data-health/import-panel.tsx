"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, CircleCheck, CircleDashed, CircleX, Download, FileSpreadsheet, History, TriangleAlert, Upload } from "lucide-react";

import { CopyButton } from "@/components/pulso/copy-button";
import { EmptyState } from "@/components/pulso/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { $api, isProblem } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { fileUpload, useRefreshAdmin, useSources } from "./api";
import { Panel, PanelError, Pill } from "./atoms";
import { IMPORT_MAX_BYTES, commitBlocker, defaultImportSource, importOutcome, previewSummary, type ImportPreview } from "./model";

// CSV import (P1-11b, vault Features/CSV Export & Import): choose or drop a file, it is checked at once
// (validation only, nothing written), then one click imports it as a `csv` collector run. A preview always
// matches the selected source and file: changing either checks again, so a stale preview is never shown.
export function ImportPanel({ onOpen }: { onOpen: (key: string) => void }) {
  const sources = useSources();
  const refresh = useRefreshAdmin();
  const preview = $api.useMutation("post", "/v1/admin/sources/{key}/import/preview");
  const commit = $api.useMutation("post", "/v1/admin/sources/{key}/import");
  const [picked, setPicked] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [tooBig, setTooBig] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const openRuns = useRef<HTMLButtonElement>(null);
  const ids = useId();
  useTakeLostFocus(openRuns, commit.data);

  const importable = sources.data?.filter((s) => s.csv_import != null) ?? [];
  const source = importable.find((s) => s.key === picked) ?? defaultImportSource(importable);

  function check(next: File, key: string) {
    setFile(next);
    commit.reset();
    preview.reset();
    setTooBig(next.size > IMPORT_MAX_BYTES);
    if (next.size <= IMPORT_MAX_BYTES) preview.mutate(fileUpload(key, next));
  }

  function importFile() {
    if (!source || !file) return;
    commit.mutate(fileUpload(source.key, file), {
      onSuccess: () => {
        setFile(null);
        preview.reset();
        void refresh();
      },
    });
  }

  let body: React.ReactNode;
  if (sources.isPending) {
    body = (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-8 w-64 max-w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  } else if (sources.isError) {
    body = <PanelError title="Couldn't load import sources" error={sources.error} retry={() => sources.refetch()} />;
  } else if (!source) {
    body = (
      <EmptyState icon={FileSpreadsheet} size="sm" title="No source has a CSV template yet">
        Templates arrive with each source&apos;s adapter (Shopify stores, CJ, Google Trends, Frankfurter FX).
      </EmptyState>
    );
  } else {
    const blocker = preview.data && commitBlocker(source, preview.data);
    const outcome = commit.data && importOutcome(commit.data, source.name);
    const failed = preview.isError && file ? failure(preview.error, CHECK_FAILED) : commit.isError ? failure(commit.error, IMPORT_FAILED) : null;
    // One short announcement per step, in one region only: failures are assertive, progress and results
    // polite (aud-004 C2-01). A failure empties the status, so a stale preview summary is never re-read.
    const alert = tooBig
      ? TOO_BIG
      : failed
        ? `${failed.text}${failed.retry ? " Select Retry to try again." : ""}`
        : outcome?.tone === "error"
          ? outcome.text
          : "";
    const status = alert
      ? ""
      : preview.isPending && file
        ? `Checking ${file.name}…`
        : commit.isPending && file
          ? `Importing ${file.name}…`
          : preview.data
            ? [previewSummary(preview.data), blocker].filter(Boolean).join(". ")
            : (outcome?.text ?? "");
    body = (
      <div className="flex flex-col gap-4 p-4">
        <div className="flex flex-wrap items-end gap-x-3 gap-y-2">
          <div className="flex w-full min-w-0 flex-col gap-1 sm:w-64">
            <label htmlFor={`${ids}-source`} className="text-label font-medium text-muted-foreground">
              Source
            </label>
            <div className="relative">
              <select
                id={`${ids}-source`}
                value={source.key}
                onChange={(e) => {
                  setPicked(e.target.value);
                  commit.reset();
                  if (file) check(file, e.target.value);
                }}
                className="h-(--input-h) w-full appearance-none rounded-md border border-border bg-secondary pr-8 pl-3 text-data text-foreground hover:border-border-strong"
              >
                {importable.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.csv_import === "ready" ? s.name : `${s.name} (check only)`}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            </div>
          </div>
          <Button asChild variant="ghost">
            <a href={`/api/v1/admin/sources/${source.key}/import/template`} download={`${source.key}-template.csv`}>
              <Download aria-hidden />
              Download template
            </a>
          </Button>
          {source.csv_import !== "ready" && (
            // "No source yet" (vault Design/UI States): why, and the part that works now. Import points here.
            <p id={`${ids}-blocker`} className="flex basis-full flex-wrap items-center gap-2 text-data text-muted-foreground">
              <Pill tone="muted" icon={CircleDashed}>
                No import adapter yet
              </Pill>
              Check a file now; importing into {source.name} arrives with its adapter.
            </p>
          )}
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const dropped = e.dataTransfer.files[0];
            if (dropped) check(dropped, source.key);
          }}
          className={cn(
            "flex flex-col items-center gap-3 rounded-lg border border-dashed border-border-strong px-5 py-4 text-center transition-transform duration-(--duration-fast) ease-standard sm:flex-row sm:text-left",
            dragging && "border-brand bg-brand-muted motion-safe:scale-[1.01]",
          )}
        >
          <div className="grid size-10 shrink-0 place-items-center rounded-lg border border-border bg-secondary text-muted-foreground">
            <Upload className="size-5" aria-hidden />
          </div>
          <div className="flex min-w-0 flex-col gap-0.5">
            <p className="text-body font-medium break-all text-foreground">{file ? file.name : "Drop a CSV here, or choose one"}</p>
            <p className="text-data text-muted-foreground">
              {file
                ? `${fileSize(file.size)} · checked against the ${source.name} template`
                : "UTF-8, comma or semicolon separated, up to 20 MB. Nothing is written until you import."}
            </p>
          </div>
          <input
            ref={input}
            type="file"
            accept=".csv,text/csv"
            hidden // "Choose CSV…" opens it
            onChange={(e) => {
              const chosen = e.target.files?.[0];
              e.target.value = ""; // choosing the same file again still checks it
              if (chosen) check(chosen, source.key);
            }}
          />
          <Button variant="secondary" size="sm" className="sm:ml-auto" onClick={() => input.current?.click()}>
            {file ? "Choose another…" : "Choose CSV…"}
          </Button>
        </div>

        <p role="status" className="sr-only">
          {status}
        </p>
        <p role="alert" className="sr-only">
          {alert}
        </p>
        <div className="flex flex-col gap-3 empty:hidden">
          {tooBig && <p className="text-data text-negative">{TOO_BIG}</p>}
          {preview.isPending && file && (
            <>
              <p className="text-data text-muted-foreground">Checking {file.name}…</p>
              <Skeleton className="h-16 w-full" />
            </>
          )}
          {preview.isError && file && (
            <ErrorLine error={preview.error} retry={() => check(file, source.key)} fallback={CHECK_FAILED} />
          )}
          {preview.data && file && (
            <PreviewResult
              preview={preview.data}
              blocker={blocker ?? null}
              blockerId={`${ids}-blocker`}
              blockerShown={source.csv_import !== "ready"}
              pending={commit.isPending}
              onImport={importFile}
            />
          )}
          {commit.isError && <ErrorLine error={commit.error} retry={importFile} fallback={IMPORT_FAILED} />}
          {outcome && (
            <div
              className={cn(
                "flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border px-4 py-3 text-data",
                outcome.tone === "error" ? "border-negative/40 bg-negative-muted" : "border-border bg-secondary",
              )}
            >
              {outcome.tone === "error" ? <CircleX className="size-4 text-negative" aria-hidden /> : <CircleCheck className="size-4 text-muted-foreground" aria-hidden />}
              <p className="min-w-0 flex-1 text-foreground">{outcome.text}</p>
              <Button ref={openRuns} size="sm" variant="secondary" onClick={() => onOpen(source.key)}>
                <History aria-hidden />
                Open runs
              </Button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <Panel id="import" title="CSV import" note="Every source has a CSV fallback (§4.2)">
      {body}
    </Panel>
  );
}

function PreviewResult({
  preview,
  blocker,
  blockerId,
  blockerShown,
  pending,
  onImport,
}: {
  preview: ImportPreview;
  blocker: string | null;
  blockerId: string;
  /** The panel already shows the blocker (no import adapter), under `blockerId`. */
  blockerShown: boolean;
  pending: boolean;
  onImport: () => void;
}) {
  const unavailable = blocker != null || pending;
  const importButton = useRef<HTMLButtonElement>(null);
  useTakeLostFocus(importButton); // e.g. after a preview Retry, whose line this result replaces
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="neutral" icon={CircleCheck}>
          {preview.valid.toLocaleString("en-US")} valid
        </Pill>
        <Pill tone={preview.invalid > 0 ? "negative" : "neutral"} icon={CircleX}>
          {preview.invalid.toLocaleString("en-US")} invalid
        </Pill>
        {preview.skipped > 0 && (
          <Pill tone="muted" icon={CircleDashed}>
            {preview.skipped.toLocaleString("en-US")} blank skipped
          </Pill>
        )}
        <Button
          ref={importButton}
          variant="primary"
          size="sm"
          className="ml-auto aria-disabled:pointer-events-auto aria-disabled:cursor-not-allowed"
          aria-disabled={unavailable}
          aria-describedby={blocker ? blockerId : undefined}
          onClick={() => !unavailable && onImport()}
        >
          {pending ? "Importing…" : `Import ${preview.valid.toLocaleString("en-US")} ${preview.valid === 1 ? "row" : "rows"}`}
        </Button>
      </div>
      {blocker && !blockerShown && (
        <p id={blockerId} className="text-data text-muted-foreground">
          {blocker}
        </p>
      )}
      {preview.errors.length > 0 && (
        <div tabIndex={0} role="region" aria-label="Row errors" className="max-h-64 overflow-auto rounded-lg border border-border">
          <table className="w-full border-collapse text-data">
            <thead className="sticky top-0 bg-card">
              <tr className="text-left text-label text-muted-foreground">
                <th className="h-8 border-b border-border px-3 text-right font-medium">Row</th>
                <th className="h-8 border-b border-border px-3 font-medium">Column</th>
                <th className="h-8 w-full border-b border-border px-3 font-medium">Problem</th>
              </tr>
            </thead>
            <tbody>
              {preview.errors.map((e, i) => (
                <tr key={i} className="border-b border-border-subtle last:border-0">
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums">{e.row}</td>
                  <td className="px-3 py-1.5 font-mono whitespace-nowrap text-muted-foreground">{e.column || "—"}</td>
                  <td className="px-3 py-1.5 text-foreground">{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {preview.error_count > preview.errors.length && (
        <p className="text-label text-subtle-foreground">
          Showing the first {preview.errors.length} of {preview.error_count.toLocaleString("en-US")} errors.
        </p>
      )}
    </>
  );
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  return kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(1)} MB`;
}

const TOO_BIG = "This file is over 20 MB. Split it into smaller files and import each.";
const CHECK_FAILED = "The API didn't answer while checking the file.";
const IMPORT_FAILED = "The API didn't answer while importing.";

/** A failed request in words. A 422 is about the file itself: retrying the same bytes can't help. */
function failure(error: unknown, fallback: string) {
  const problem = isProblem(error) ? error : null;
  return { problem, text: problem ? problem.detail : fallback, retry: problem?.status !== 422 };
}

/**
 * Focuses `ref` once `when` holds, but only when nothing has focus (aud-004 C2-02): the control a keyboard
 * user just used (Import, Retry) left with the step it belonged to. Never takes focus from another control.
 */
function useTakeLostFocus(ref: React.RefObject<HTMLElement | null>, when: unknown = true) {
  useEffect(() => {
    if (when && document.activeElement === document.body) ref.current?.focus();
  }, [ref, when]);
}

function ErrorLine({ error, retry, fallback }: { error: unknown; retry: () => void; fallback: string }) {
  const { problem, text, retry: retryable } = failure(error, fallback);
  const retryButton = useRef<HTMLButtonElement>(null);
  useTakeLostFocus(retryButton); // a Retry that failed again comes back focused
  return (
    // Spoken by the panel's alert region, with the Retry hint; this line has no live role of its own.
    // One row when it fits. Narrower, the message keeps 12rem beside the icon and the ID, then the actions,
    // wrap below it at full width: beside the icon a uuid4 ID doesn't fit at 375px.
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-negative/40 bg-negative-muted px-4 py-3 text-data">
      <TriangleAlert className="size-4 text-negative" aria-hidden />
      <p className="min-w-0 flex-[1_1_12rem] text-foreground">{text}</p>
      {problem && (
        <p className="font-mono text-label text-subtle-foreground">
          {/* inline-block: the ID moves to its own line whole instead of breaking at a hyphen. */}
          Error ID <span className="inline-block max-w-full select-all break-all selection:text-foreground">{problem.request_id}</span>
        </p>
      )}
      <div className="ml-auto flex gap-2">
        {retryable && (
          <Button ref={retryButton} size="sm" variant="secondary" onClick={retry}>
            Retry
          </Button>
        )}
        {problem && <CopyButton value={problem.request_id} label="Copy error ID" />}
      </div>
    </div>
  );
}
