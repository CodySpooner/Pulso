import type { components } from "@/lib/api/schema";

// The Settings form (UX-10, DEC-251): the owner types percent and dollars, the API takes basis points and USD minor
// units. Text is parsed digit by digit, never through a float, so 2.9% is exactly 290 bps and $0.30 is 30.

export type Settings = components["schemas"]["SettingsResponse"];
export type SettingsPatch = components["schemas"]["SettingsPatch"];

export type PercentField = "payment_fee_bps" | "shopify_fee_bps" | "target_margin_bps" | "returns_bps" | "duty_default_bps";
export type MoneyField = "payment_fee_fixed_minor" | "default_cpa_minor" | "customs_fee_minor";
export type Field = PercentField | MoneyField;

export const PERCENT_FIELDS: readonly PercentField[] = ["payment_fee_bps", "shopify_fee_bps", "target_margin_bps", "returns_bps", "duty_default_bps"];
export const MONEY_FIELDS: readonly MoneyField[] = ["payment_fee_fixed_minor", "default_cpa_minor", "customs_fee_minor"];
/** Form order: errors focus the first invalid field in this order. */
export const FIELDS: readonly Field[] = [
  "payment_fee_bps",
  "payment_fee_fixed_minor",
  "shopify_fee_bps",
  "default_cpa_minor",
  "target_margin_bps",
  "duty_default_bps",
  "customs_fee_minor",
  "returns_bps",
];

/** Duty can pass 100% (DEC-237 h); the API caps it at 1,000%, like the Profit override (DEC-246 g). */
export const MAX_BPS: Record<PercentField, number> = {
  payment_fee_bps: 10_000,
  shopify_fee_bps: 10_000,
  target_margin_bps: 10_000,
  returns_bps: 10_000,
  duty_default_bps: 100_000,
};

/** What the owner typed, field by field, plus whether duty is set at all (null duty is "not set", never 0). */
export interface Draft {
  values: Record<Field, string>;
  dutySet: boolean;
}

/** Two-decimal text to hundredths: "2.9" → 290, ".5" → 50. Null when it isn't a plain non-negative number. */
function toHundredths(text: string, maxWhole: number): number | null {
  const match = /^(\d*)(?:\.(\d{0,2}))?$/.exec(text.trim());
  if (!match || (match[1] === "" && !match[2]) || match[1].length > maxWhole) return null;
  return Number(match[1] || 0) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
}

/** "2.9" → 290 bps. */
export const percentToBps = (text: string): number | null => toHundredths(text, 7);
/** "0.30" → 30 cents (USD's exponent is 2). At most nine whole digits, so the value stays an exact JS integer. */
export const dollarsToMinor = (text: string): number | null => toHundredths(text, 9);

/** 290 → "2.9", 2000 → "20", 5 → "0.05": no trailing zeros. */
export function bpsToPercent(bps: number): string {
  const cents = bps % 100;
  return cents === 0 ? String(Math.trunc(bps / 100)) : `${Math.trunc(bps / 100)}.${String(cents).padStart(2, "0").replace(/0$/, "")}`;
}

/** 30 → "0.30", 1500 → "15.00". */
export const minorToDollars = (minor: number): string => `${Math.trunc(minor / 100)}.${String(minor % 100).padStart(2, "0")}`;

export function toDraft(settings: Settings): Draft {
  const values = {} as Record<Field, string>;
  for (const key of PERCENT_FIELDS) values[key] = bpsToPercent(settings[key] ?? 0);
  for (const key of MONEY_FIELDS) values[key] = minorToDollars(settings[key]);
  // An unset duty opens with an empty box, so choosing "Set a rate" never pre-fills a 0 the owner didn't type.
  if (settings.duty_default_bps === null) values.duty_default_bps = "";
  return { values, dutySet: settings.duty_default_bps !== null };
}

/** The field's problem in words, or null. An unset duty has nothing to check. */
export function fieldError(draft: Draft, key: Field): string | null {
  if (key === "duty_default_bps" && !draft.dutySet) return null;
  const text = draft.values[key].trim();
  const money = (MONEY_FIELDS as readonly string[]).includes(key);
  if (text === "") return money ? "Enter an amount. Use 0 for none." : key === "duty_default_bps" ? "Enter a duty rate. 0% is a valid rate." : "Enter a percentage. Use 0 for none.";
  if (text.startsWith("-")) return "Can't be negative.";
  if (/^\d*\.\d{3,}$/.test(text)) return money ? "Use whole cents: at most 2 decimals." : "Use at most 2 decimals.";
  const value = money ? dollarsToMinor(text) : percentToBps(text);
  if (value === null) return money ? "Enter an amount in dollars, like 0.30." : "Enter a number, like 2.9.";
  if (!money && value > MAX_BPS[key as PercentField]) return `Enter ${(MAX_BPS[key as PercentField] / 100).toLocaleString("en-US")}% or less.`;
  return null;
}

export function errors(draft: Draft): Partial<Record<Field, string>> {
  return Object.fromEntries(FIELDS.flatMap((key) => {
    const error = fieldError(draft, key);
    return error ? [[key, error]] : [];
  }));
}

/** The PATCH body: every editable field, so a save sends the whole form. Null while any field is invalid. */
export function toBody(draft: Draft): SettingsPatch | null {
  if (Object.keys(errors(draft)).length) return null;
  const v = draft.values;
  return {
    payment_fee_bps: percentToBps(v.payment_fee_bps)!,
    payment_fee_fixed_minor: dollarsToMinor(v.payment_fee_fixed_minor)!,
    shopify_fee_bps: percentToBps(v.shopify_fee_bps)!,
    default_cpa_minor: dollarsToMinor(v.default_cpa_minor)!,
    target_margin_bps: percentToBps(v.target_margin_bps)!,
    duty_default_bps: draft.dutySet ? percentToBps(v.duty_default_bps)! : null,
    returns_bps: percentToBps(v.returns_bps)!,
    customs_fee_minor: dollarsToMinor(v.customs_fee_minor)!,
  };
}

/** True when saving would change something: "2.90" against a saved 290 is not a change. */
export function isDirty(draft: Draft, saved: Settings): boolean {
  if (draft.dutySet !== (saved.duty_default_bps !== null)) return true;
  return FIELDS.some((key) => {
    if (key === "duty_default_bps" && !draft.dutySet) return false;
    const text = draft.values[key];
    const value = (MONEY_FIELDS as readonly string[]).includes(key) ? dollarsToMinor(text) : percentToBps(text);
    return value !== saved[key];
  });
}

/** A 422 problem's `errors` mapped to the fields they name (`loc` = ["body", field]). */
export function apiFieldErrors(errors: Record<string, unknown>[] | undefined): Partial<Record<Field, string>> {
  const out: Partial<Record<Field, string>> = {};
  for (const error of errors ?? []) {
    const loc = error.loc;
    const key = Array.isArray(loc) ? loc[1] : undefined;
    if (typeof key === "string" && (FIELDS as readonly string[]).includes(key) && typeof error.msg === "string") out[key as Field] ??= error.msg;
  }
  return out;
}
