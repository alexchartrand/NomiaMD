import type { ExtractedFee } from "../../../api";

// One entry of a code's fee selector: a fee at one of its lieux. A fee listing several
// lieux yields one option per lieu; `lieu` is null for a fee with at most one.
export interface FeeOption {
  feeIndex: number;
  lieu: string | null;
  label: string;
}

export function formatAmount(fee: ExtractedFee): string {
  if (fee.unit === "unités") return `${fee.amount_text ?? fee.amount ?? "?"} unités`;
  return fee.amount != null ? `${fee.amount.toFixed(2)} $` : (fee.amount_text ?? "?");
}

function joinParts(parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join(" — ");
}

function feeDetails(fee: ExtractedFee): string {
  return joinParts([
    fee.role != null ? `R = ${fee.role}` : null,
    fee.context,
    fee.majoration ? `majoration ${fee.majoration}` : null,
  ]);
}

// The lieu a fee defaults to when the physician hasn't picked one: its first, if it lists several.
export function defaultLieu(fee: ExtractedFee): string | null {
  return fee.lieux.length > 1 ? fee.lieux[0] : null;
}

// Options are labelled by lieu ("Autre" when the fee has none). Options sharing a label get
// the role/context appended, and the amount if that still isn't enough.
export function buildFeeOptions(fees: ExtractedFee[]): FeeOption[] {
  const base = fees.flatMap((fee, feeIndex): FeeOption[] =>
    fee.lieux.length > 1
      ? fee.lieux.map((lieu) => ({ feeIndex, lieu, label: lieu }))
      : [{ feeIndex, lieu: null, label: fee.lieux[0] ?? "Autre" }],
  );
  const count = (labels: string[], label: string) => labels.filter((l) => l === label).length;
  const labels = base.map((o) => o.label);
  const detailed = base.map((o) => (count(labels, o.label) > 1 ? joinParts([o.label, feeDetails(fees[o.feeIndex])]) : o.label));
  return base.map((o, i) => ({
    ...o,
    label: count(detailed, detailed[i]) > 1 ? joinParts([detailed[i], formatAmount(fees[o.feeIndex])]) : detailed[i],
  }));
}

export function optionValue(feeIndex: number, lieu: string | null): string {
  return lieu ? `${feeIndex}|${lieu}` : String(feeIndex);
}
