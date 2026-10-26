import { BookOpen } from "lucide-react";

import { SelectableId } from "@/components/pulso/copy-button";
import { EmptyState } from "@/components/pulso/empty-state";
import { PageHeader } from "@/components/pulso/page-header";
import { StatusDot } from "@/components/pulso/status-dot";
import { cn } from "@/lib/utils";

import { every, formatValue, isBuilt, sections, span, term, type Block, type BuiltScore, type Field, type MethodologyDoc, type PlannedScore } from "./model";

const card = "scroll-mt-18 rounded-xl border border-border bg-card shadow-card lg:scroll-mt-4 target:border-border-strong";
const cardHead = "flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border-subtle px-4 py-3 md:px-6";
const th = "border-b border-border px-3 font-medium whitespace-nowrap";
const td = "border-b border-border-subtle px-3 py-1.5 align-top";
const link = "link-inline rounded-sm text-foreground underline decoration-border-strong underline-offset-2 hover:decoration-current";

/** Docstring text with its `code` spans set in mono. */
function Prose({ text }: { text: string }) {
  return text.split("`").map((part, i) => (i % 2 ? <code key={i} className="rounded-sm bg-secondary px-1 text-data text-foreground">{part}</code> : part));
}

/** A docstring's paragraphs and lists as the export splits them; a rule's name leads its list item. */
function Doc({ blocks, lede = false }: { blocks: Block[]; lede?: boolean }) {
  return (
    <div className="flex max-w-[68ch] flex-col gap-3 text-muted-foreground">
      {blocks.map((block, i) =>
        "text" in block ? (
          <p key={i} className={cn(lede && i === 0 && "text-foreground")}>
            <Prose text={block.text} />
          </p>
        ) : (
          <ul key={i} className="flex flex-col gap-1.5 border-l border-border pl-4">
            {block.items.map((item) => {
              const [name, rest] = term(item);
              return (
                <li key={item}>
                  {name && <span className="font-medium text-foreground">{name}: </span>}
                  <Prose text={rest} />
                </li>
              );
            })}
          </ul>
        ),
      )}
    </div>
  );
}

function Status({ built, children }: { built: boolean; children: React.ReactNode }) {
  return (
    <span className="inline-flex h-5 items-center gap-1.5 rounded-full border border-border-subtle px-2 font-sans text-micro font-medium whitespace-nowrap text-muted-foreground">
      <StatusDot state={built ? "ok" : "disabled"} className="size-1.5" />
      {children}
    </span>
  );
}

function Sub({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h3 className="text-data font-semibold text-foreground">{title}</h3>
        {note && <code className="min-w-0 break-all text-label text-subtle-foreground">{note}</code>}
      </div>
      {children}
    </div>
  );
}

interface Row {
  name: string;
  note?: string | null;
  value: React.ReactNode;
  title?: string;
}

// Terminal-dense reference rows (vault Design/Tables & Data Density): the name with its code comment under it, and
// the value or type right-aligned in mono, so no table needs to scroll sideways at 375px. Below sm a type wraps at its
// spaces (a value never does): on one line, Mapping[UUID, Sequence[int]] made the inputs table wider than its card.
function Rows({ label, columns, rows }: { label: string; columns: [string, string]; rows: Row[] }) {
  return (
    <table aria-label={label} className="w-full border-separate border-spacing-0 zone-data">
      <thead>
        <tr className="row-h-compact text-label text-muted-foreground">
          <th scope="col" className={cn(th, "text-left")}>
            {columns[0]}
          </th>
          <th scope="col" className={cn(th, "text-right")}>
            {columns[1]}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name} className="row-h">
            <th scope="row" className={cn(td, "text-left font-normal")}>
              <code className="text-foreground">{row.name}</code>
              {row.note && (
                <span className="block text-label text-muted-foreground">
                  <Prose text={row.note} />
                </span>
              )}
            </th>
            <td className={cn(td, "num font-mono whitespace-nowrap text-foreground")} title={row.title}>
              {row.value}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const typed = (fields: Field[]): Row[] =>
  fields.map((f) => ({ name: f.name, note: f.note, value: <span className="text-muted-foreground max-sm:whitespace-normal">{f.type}</span> }));

function ScoreSection({ score, missing }: { score: BuiltScore; missing: string }) {
  const config = score.code.replace(/\.\w+$/, ".Config");
  return (
    <section id={score.id} aria-labelledby={`${score.id}-title`} className={card}>
      <header className={cardHead}>
        <h2 id={`${score.id}-title`} className="text-title-3 font-semibold text-foreground">
          {score.title}
        </h2>
        <Status built>Built · {score.task}</Status>
        <span className="flex min-w-0 items-center gap-2 text-label text-muted-foreground sm:ml-auto">
          model_version
          <SelectableId
            value={score.model_version}
            label={`${score.title} model_version`}
            title={`SHA-256 of the config: ${score.config_digest}`}
            className="font-mono text-data text-foreground"
          />
        </span>
      </header>
      <div className="flex flex-col gap-5 p-4 md:p-6">
        <Doc blocks={score.definition} lede />
        <div className="grid gap-6 xl:grid-cols-2">
          <Sub title="Config" note={config}>
            <Rows
              label={`${score.title} config`}
              columns={["Setting", "Value"]}
              rows={score.config.map((c) => ({
                name: c.name,
                note: c.note,
                value: formatValue(c.value),
                title: `${String(c.value)} · ${config}.${c.name} · model_version ${score.model_version}`,
              }))}
            />
          </Sub>
          <Sub title="Inputs" note={score.code}>
            <Rows label={`${score.title} inputs`} columns={["Input", "Type"]} rows={typed(score.inputs.map((i) => ({ ...i, note: null })))} />
          </Sub>
        </div>
        <Sub title="Missing inputs">
          <p className="max-w-[68ch] text-muted-foreground">
            <Prose text={missing} />{" "}
            <a href="#explanation" className={link}>
              How explanations record them
            </a>
          </p>
        </Sub>
      </div>
    </section>
  );
}

// One card for every score with no code yet, a row each; a row's id is its anchor, so links land on it already.
function Planned({ scores }: { scores: PlannedScore[] }) {
  return (
    <section aria-labelledby="not-built-title" className={card}>
      <header className={cardHead}>
        <h2 id="not-built-title" className="text-title-3 font-semibold text-foreground">
          Not built yet
        </h2>
        <span className="text-label text-muted-foreground">Pulso shows no number for these until their code ships.</span>
      </header>
      <ul>
        {scores.map((score) => (
          <li
            key={score.id}
            id={score.id}
            className="flex scroll-mt-18 flex-wrap items-center gap-x-3 gap-y-1 border-b border-border-subtle px-4 py-2.5 last:border-b-0 target:bg-accent md:px-6 lg:scroll-mt-4"
          >
            <h3 className="text-body font-medium text-foreground">{score.title}</h3>
            <span className="text-label text-muted-foreground tabular-nums sm:ml-auto">
              Phase {score.phase}
              {score.task && ` · ${score.task}`}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Section({ id, title, aside, children }: { id: string; title: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={card}>
      <header className={cardHead}>
        <h2 id={`${id}-title`} className="text-title-3 font-semibold text-foreground">
          {title}
        </h2>
        {aside}
      </header>
      <div className="flex flex-col gap-5 p-4 md:p-6">{children}</div>
    </section>
  );
}

// Each source's cadence and the ages its inputs count 1 to and go stale after (Score Definitions §6). The cadence sits
// under the source so three columns fit a 375px card; between the two ages an input counts 0.5.
function Cadences({ confidence }: { confidence: MethodologyDoc["contract"]["confidence"] }) {
  if (confidence.cadence.length === 0)
    return <p className="text-data text-muted-foreground">No source has a cadence yet, so every input counts as fresh.</p>;
  return (
    <table aria-label="Source cadences" className="w-full border-separate border-spacing-0 zone-data">
      <thead>
        <tr className="row-h-compact text-label text-muted-foreground">
          <th scope="col" className={cn(th, "text-left")}>
            Source
          </th>
          <th scope="col" className={cn(th, "text-right")}>
            Fresh to
          </th>
          <th scope="col" className={cn(th, "text-right")}>
            Stale after
          </th>
        </tr>
      </thead>
      <tbody>
        {confidence.cadence.map((c) => (
          <tr key={c.source} className="row-h">
            <th scope="row" className={cn(td, "text-left font-normal")}>
              <code className="text-foreground">{c.source}</code>
              <span className="block text-label text-muted-foreground">
                {every(c.days)}
                {c.score && " · score row Opportunity reads"}
              </span>
            </th>
            <td className={cn(td, "num font-mono whitespace-nowrap text-foreground")} title={`${confidence.fresh_within} × ${every(c.days)}: counts 1`}>
              {span(c.days * confidence.fresh_within)}
            </td>
            <td className={cn(td, "num font-mono whitespace-nowrap text-foreground")} title={`${confidence.stale_after} × ${every(c.days)}: missing, never 0`}>
              {span(c.days * confidence.stale_after)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Contents({ doc }: { doc: MethodologyDoc }) {
  return (
    <nav aria-label="On this page" className="min-w-0 lg:sticky lg:top-6 lg:col-start-2 lg:row-start-1">
      <p className="mb-2 hidden text-label font-medium text-subtle-foreground lg:block">On this page</p>
      {/* A phone gets one swipeable row (the cut chip at the edge shows there's more); py-1.5 holds the touch hit areas. */}
      <ul className="-my-1.5 flex gap-2 overflow-x-auto py-1.5 lg:my-0 lg:flex-col lg:gap-0 lg:overflow-visible lg:border-l lg:border-border-subtle lg:py-0">
        {sections(doc).map((s) => (
          <li key={s.id} className="shrink-0">
            <a
              href={`#${s.id}`}
              className={cn(
                "relative hit-area inline-flex h-8 items-center rounded-md whitespace-nowrap border border-border-subtle px-2.5 text-label font-medium transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong hover:text-foreground",
                "lg:-ml-px lg:flex lg:h-7 lg:rounded-none lg:border-0 lg:border-l lg:border-transparent lg:px-3",
                s.built ? "text-muted-foreground" : "text-subtle-foreground",
              )}
            >
              {s.title}
              {!s.built && <span className="sr-only"> (not built yet)</span>}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

// MT-1 (DEC-313): every score's definition, inputs, thresholds and version, rendered from the export of the scoring
// code. A section's id is its stable anchor for "How this is computed" links.
export function Methodology({ doc, description }: { doc: MethodologyDoc; description: string }) {
  const built = doc.scores.filter(isBuilt);
  const planned = doc.scores.filter((s): s is PlannedScore => !isBuilt(s));
  const { contract } = doc;
  return (
    <div className="flex w-full max-w-280 flex-col gap-6">
      <PageHeader
        title="Methodology"
        description={description}
        meta={
          // One span: the meta row is a flex row, which would space out every text run and code span.
          <span>
            Generated from <code>pulso_ml.scores</code> and <code>{contract.code}</code>; CI fails when it drifts from the code
          </span>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_12rem] lg:items-start">
        <Contents doc={doc} />
        <div className="flex min-w-0 flex-col gap-6 lg:col-start-1 lg:row-start-1">
          {built.length === 0 && (
            <section aria-label="Scores" className={card}>
              <EmptyState icon={BookOpen} headingLevel="h2" title="No score is built yet">
                Each score&apos;s definition, inputs and thresholds appear here from its code as it ships.
              </EmptyState>
            </section>
          )}
          {built.map((score) => (
            <ScoreSection key={score.id} score={score} missing={contract.missing_inputs.text} />
          ))}
          {planned.length > 0 && <Planned scores={planned} />}
          <Section id="explanation" title="Explanation contract" aside={<code className="text-label text-subtle-foreground">{contract.code}</code>}>
            <Doc blocks={contract.explanation.definition} />
            <div className="grid gap-6 xl:grid-cols-2">
              <Sub title="Every score row" note="Explanation">
                <Rows label="Explanation fields" columns={["Field", "Type"]} rows={typed(contract.explanation.fields)} />
              </Sub>
              <Sub title="Each input" note="Component">
                <Rows label="Component fields" columns={["Field", "Type"]} rows={typed(contract.component.fields)} />
              </Sub>
            </div>
            <Sub title="Missing inputs" note="explain()">
              <Doc blocks={[contract.missing_inputs, ...contract.renormalisation]} />
            </Sub>
            <Sub title="Versioning" note="version()">
              <Doc blocks={contract.versioning} />
            </Sub>
          </Section>
          <Section id="confidence" title="Confidence" aside={<code className="min-w-0 break-all text-label text-subtle-foreground">{contract.confidence.code}</code>}>
            <p className="max-w-[68ch] rounded-lg border border-border-subtle bg-secondary px-3 py-2 font-mono text-data text-foreground">
              {contract.confidence.formula.replace(/\.$/, "")}
            </p>
            <Doc blocks={contract.confidence.definition} />
            <div className="grid gap-6 xl:grid-cols-2">
              <Sub title="Freshness" note="fresh()">
                <Doc blocks={contract.confidence.freshness} />
              </Sub>
              <Sub title="Cadence" note="CADENCE">
                <Cadences confidence={contract.confidence} />
              </Sub>
            </div>
          </Section>
          <Section id="limitations" title="Known limitations">
            <ul className="flex max-w-[68ch] flex-col gap-1.5 border-l border-border pl-4 text-muted-foreground">
              {doc.limitations.map((item) => (
                <li key={item}>
                  <Prose text={item} />
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
