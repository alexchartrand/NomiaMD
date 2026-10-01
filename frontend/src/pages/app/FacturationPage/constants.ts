import type { ClaimCodeLine, ClaimStatus } from "../../../api";

export const STATUS_LABELS: Record<ClaimStatus, string> = {
  brouillon: "Brouillon",
  soumis: "Soumis",
};

// The snapshotted fee's details beyond its dollar amount — a unit count (never billed as
// dollars), the manual's role column, its context and lieux.
export function describeFee(line: ClaimCodeLine): string | null {
  const parts: string[] = [];
  if (line.fee_unit && line.fee_unit !== "dollars" && line.fee_units != null) {
    parts.push(`${line.fee_units} ${line.fee_unit}`);
  }
  if (line.fee_role != null) parts.push(`R = ${line.fee_role}`);
  if (line.fee_context) parts.push(line.fee_context);
  if (line.fee_lieux?.length) parts.push(line.fee_lieux.join(", "));
  return parts.length ? parts.join(" — ") : null;
}
