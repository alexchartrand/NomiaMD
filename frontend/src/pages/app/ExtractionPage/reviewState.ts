import type { BillingExtractionResponse } from "../../../api";

// Everything derived from a single extraction result, from the moment it comes back
// through patient/date selection to the save outcome — grouped so a fresh extraction or a
// cleared transcript resets all of it atomically instead of via a scattered list of setters.
export interface ReviewState {
  result: BillingExtractionResponse | null;
  selectedRosterId: number | "";
  serviceDate: string;
  selection: Set<number>;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
}

export const initialReviewState: ReviewState = {
  result: null,
  selectedRosterId: "",
  serviceDate: "",
  selection: new Set(),
  saving: false,
  saveError: null,
  saved: false,
};

export type ReviewAction =
  | { type: "extracted"; result: BillingExtractionResponse }
  | { type: "cleared" }
  | { type: "roster-selected"; id: number | "" }
  | { type: "service-date-changed"; date: string }
  | { type: "code-toggled"; index: number }
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
        selectedRosterId: action.result.patient_suggestion?.matched_patient_id ?? "",
        serviceDate: action.result.encounter_date ?? "",
      };
    case "cleared":
      return initialReviewState;
    case "roster-selected":
      return { ...state, selectedRosterId: action.id };
    case "service-date-changed":
      return { ...state, serviceDate: action.date };
    case "code-toggled": {
      const selection = new Set(state.selection);
      if (selection.has(action.index)) selection.delete(action.index);
      else selection.add(action.index);
      return { ...state, selection };
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
