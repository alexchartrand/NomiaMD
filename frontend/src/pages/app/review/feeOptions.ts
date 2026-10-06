import type { ClaimCodeLine, ExtractedFee } from "../../../api";
import { formatMoney } from "../../../utils/money";

// One entry of a code's fee selector: a fee at one of its lieux. A fee listing several
// lieux yields one option per lieu; `lieu` is null for a fee with at most one.
export interface FeeOption {
  feeIndex: number;
  lieu: string | null;
  label: string;
}

export function formatAmount(fee: ExtractedFee): string {
  if (fee.unit === "unités") return `${fee.amount_text ?? fee.amount ?? "?"} unités`;
  return fee.amount != null ? formatMoney(fee.amount) : (fee.amount_text ?? "?");
}

function joinParts(parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join(" — ");
}

export function feeDetails(fee: ExtractedFee): string {
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

// A fee in "unités" is a count of anesthesia base units, not a price — it never adds to the
// dollar total, and counts as a code without a dollar amount.
export function dollarAmount(fee: ExtractedFee | null): number | null {
  return fee?.unit === "dollars" ? fee.amount : null;
}

// The indicative total of the fees picked for the selected codes (null: a code without a fee).
export function feeTotals(fees: (ExtractedFee | null)[]): { totalAmount: number; codesMissingFee: number } {
  return {
    totalAmount: fees.reduce((sum, fee) => sum + (dollarAmount(fee) ?? 0), 0),
    codesMissingFee: fees.filter((fee) => dollarAmount(fee) == null).length,
  };
}

// Whether a saved claim line snapshotted this fee — matched by role, context and amount.
export function isSameFee(fee: ExtractedFee, line: ClaimCodeLine): boolean {
  const amount = fee.unit === "dollars" ? line.fee_amount : line.fee_units;
  return fee.role === line.fee_role && fee.context === line.fee_context && fee.amount === amount;
}

// Which of a code's fees, and which lieu among that fee's several, a saved claim line kept.
// feeIndex 0 when no fee matches (the codes table changed since); lieu null for the fee's default.
export function feeFromClaimLine(fees: ExtractedFee[], line: ClaimCodeLine): { feeIndex: number; lieu: string | null } {
  const feeIndex = Math.max(fees.findIndex((fee) => isSameFee(fee, line)), 0);
  // A claim keeps a single lieu when the physician narrowed a fee that lists several.
  const claimedLieu = line.fee_lieux?.length === 1 ? line.fee_lieux[0] : null;
  return { feeIndex, lieu: claimedLieu && fees[feeIndex]?.lieux.length > 1 ? claimedLieu : null };
}
