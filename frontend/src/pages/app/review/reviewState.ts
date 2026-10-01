import type { BillingExtractionResponse } from "../../../api";

// Everything derived from a single extraction result, from the moment it comes back
// through the save outcome — grouped so a fresh extraction or a cleared transcript resets
// all of it atomically instead of via a scattered list of setters. The patient itself is
// NOT here: it's chosen before extraction runs (SourceStep.tsx) and owned by
// ExtractionPage/index.tsx's own state, since it's fixed for the whole flow rather than
// derived from a particular extraction result.
export interface ReviewState {
  result: BillingExtractionResponse | null;
  serviceDate: string;
  selection: Set<number>;
  // Code array-index -> chosen fee index, for any code with more than one fee. Not seeded
  // up front — read with `feeSelection.get(i) ?? 0`, which is also correct for a single-fee
  // or no-fee code (the index is only ever used once fees.length > 0).
  feeSelection: Map<number, number>;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
}

export const initialReviewState: ReviewState = {
  result: null,
  serviceDate: "",
  selection: new Set(),
  feeSelection: new Map(),
  saving: false,
  saveError: null,
  saved: false,
};

export type ReviewAction =
  | { type: "extracted"; result: BillingExtractionResponse }
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
        serviceDate: action.result.encounter_date ?? "",
      };
    case "cleared":
      return initialReviewState;
    case "service-date-changed":
      return { ...state, serviceDate: action.date };
    case "code-toggled": {
      const selection = new Set(state.selection);
      if (selection.has(action.index)) selection.delete(action.index);
      else selection.add(action.index);
      return { ...state, selection };
    }
    case "fee-selected": {
      const feeSelection = new Map(state.feeSelection);
      feeSelection.set(action.index, action.feeIndex);
      return { ...state, feeSelection };
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
