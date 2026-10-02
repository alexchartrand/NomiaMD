import type { BillingExtractionResponse, Claim, ClaimCodeLine, ExtractedFee } from "../../../api";

// Everything derived from a single extraction result, from the moment it's loaded through
// the save outcome — grouped so a different result resets all of it atomically instead of
// via a scattered list of setters (see useCodeReview.ts). The patient isn't here: it was
// fixed before extraction ran, so it belongs to the encounter, not to this result.
export interface ReviewState {
  result: BillingExtractionResponse | null;
  serviceDate: string;
  selection: Set<number>;
  // Code array-index -> chosen fee index, for any code with more than one fee. Not seeded
  // up front — read with `feeSelection.get(i) ?? 0`, which is also correct for a single-fee
  // or no-fee code (the index is only ever used once fees.length > 0).
  feeSelection: Map<number, number>;
  // Nothing changed since it was loaded — saving a claim's own selection again is pointless.
  pristine: boolean;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
}

export const initialReviewState: ReviewState = {
  result: null,
  serviceDate: "",
  selection: new Set(),
  feeSelection: new Map(),
  pristine: true,
  saving: false,
  saveError: null,
  saved: false,
};

export type ReviewAction =
  // `claim`: the one already saved from this encounter, whose codes start ticked.
  | { type: "extracted"; result: BillingExtractionResponse; claim?: Claim | null }
  | { type: "cleared" }
  | { type: "service-date-changed"; date: string }
  | { type: "code-toggled"; index: number }
  | { type: "fee-selected"; index: number; feeIndex: number }
  | { type: "save-started" }
  | { type: "save-succeeded" }
  | { type: "save-cancelled" }
  | { type: "save-failed"; error: string };

export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case "extracted":
      return {
        ...initialReviewState,
        result: action.result,
        serviceDate: action.claim?.service_date ?? action.result.encounter_date ?? "",
        ...(action.claim ? selectionFromClaim(action.result, action.claim) : {}),
      };
    case "cleared":
      return initialReviewState;
    case "service-date-changed":
      return { ...state, serviceDate: action.date, pristine: false };
    case "code-toggled": {
      const selection = new Set(state.selection);
      if (selection.has(action.index)) selection.delete(action.index);
      else selection.add(action.index);
      return { ...state, selection, pristine: false };
    }
    case "fee-selected": {
      const feeSelection = new Map(state.feeSelection);
      feeSelection.set(action.index, action.feeIndex);
      return { ...state, feeSelection, pristine: false };
    }
    case "save-started":
      return { ...state, saving: true, saveError: null };
    case "save-succeeded":
      return { ...state, saving: false, saved: true };
    case "save-cancelled":
      return { ...state, saving: false };
    case "save-failed":
      return { ...state, saving: false, saveError: action.error };
  }
}

// The proposed codes a saved claim kept, and the fee picked for each — matched by code, then
// by the snapshotted fee's role, context and amount. A claimed code the result doesn't
// propose (the claim came from an older run) can't be ticked and is left out.
function selectionFromClaim(
  result: BillingExtractionResponse,
  claim: Claim,
): Pick<ReviewState, "selection" | "feeSelection"> {
  const claimed = new Map(claim.codes.map((line) => [line.code, line]));
  const selection = new Set<number>();
  const feeSelection = new Map<number, number>();
  result.billing.result.codes.forEach((code, i) => {
    const line = claimed.get(code.code);
    if (!line) return;
    selection.add(i);
    const feeIndex = code.fees.findIndex((fee) => isSameFee(fee, line));
    if (feeIndex > 0) feeSelection.set(i, feeIndex);
  });
  return { selection, feeSelection };
}

function isSameFee(fee: ExtractedFee, line: ClaimCodeLine): boolean {
  const amount = fee.unit === "dollars" ? line.fee_amount : line.fee_units;
  return fee.role === line.fee_role && fee.context === line.fee_context && fee.amount === amount;
}
