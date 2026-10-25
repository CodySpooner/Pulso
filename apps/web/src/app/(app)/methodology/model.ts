import data from "@/lib/methodology.json";

export type Block = { text: string } | { items: string[] };

export interface Field {
  name: string;
  type: string;
  /** The field's line comment in the code; null when it has none. */
  note: string | null;
}

export interface BuiltScore {
  id: string;
  title: string;
  status: "built";
  task: string;
  /** The function that computes it, e.g. pulso_ml.scores.lifecycle.lifecycle_stage. */
  code: string;
  definition: Block[];
  inputs: Omit<Field, "note">[];
  config: (Field & { value: number | string | boolean })[];
  model_version: string;
  config_digest: string;
}

export interface PlannedScore {
  id: string;
  title: string;
  status: "not built yet";
  phase: number;
  task: string | null;
}

export type Score = BuiltScore | PlannedScore;

export interface MethodologyDoc {
  scores: Score[];
  contract: {
    code: string;
    explanation: { definition: Block[]; fields: Field[] };
    component: { definition: Block[]; fields: Field[] };
    missing_inputs: { text: string };
    renormalisation: Block[];
    versioning: Block[];
    confidence: { formula: string; status: string };
  };
  limitations: string[];
}

// The export `uv run python -m pulso_ml.scores.methodology` writes; test_methodology fails CI while it differs from
// the code (DEC-313), so nothing on the page is written by hand.
export const methodology = data as MethodologyDoc;

export const isBuilt = (score: Score): score is BuiltScore => score.status === "built";

/** The page's anchors in reading order: every score, then the contract, confidence and limitations. */
export function sections(doc: MethodologyDoc): { id: string; title: string; built: boolean }[] {
  return [
    ...doc.scores.map((s) => ({ id: s.id, title: s.title, built: isBuilt(s) })),
    { id: "explanation", title: "Explanation contract", built: true },
    { id: "confidence", title: "Confidence", built: true },
    { id: "limitations", title: "Known limitations", built: true },
  ];
}

/** A rule's name leads its item: "dead · no sales: at most 1 unit…" → ["dead · no sales", "at most 1 unit…"]. */
export function term(item: string): [string | null, string] {
  const at = item.indexOf(": ");
  return at > 0 && at <= 32 ? [item.slice(0, at), item.slice(at + 2)] : [null, item];
}

const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 });

/** A config value at four decimals with a true minus sign; the exact value goes in the hover. */
export function formatValue(value: number | string | boolean): string {
  return typeof value === "number" ? number.format(value).replace("-", "−") : String(value);
}
