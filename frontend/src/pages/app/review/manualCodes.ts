import type { ClaimCodeLine, CodeHit, ExtractedFee, SelectedCode } from "../../../api";
import { defaultLieu, feeFromClaimLine } from "./feeOptions";

// The codes the physician added from the code search, and the fee picked for each — on an
// encounter's review (beside the extraction's suggestions, reviewState.ts) or on a claim billed
// without an encounter (FacturerPage). Keyed by code number: a code is added at most once.
export interface ManualCodesState {
  codes: CodeHit[];
  // Absent = the code's first fee (see ReviewState.feeSelection).
  feeSelection: Map<string, number>;
  // Absent = the fee's first lieu, when it lists several.
  lieuSelection: Map<string, string>;
}

export const emptyManualCodes: ManualCodesState = {
  codes: [],
  feeSelection: new Map(),
  lieuSelection: new Map(),
};

export type ManualCodesAction =
  | { type: "manual-code-added"; hit: CodeHit }
  | { type: "manual-code-removed"; number: string }
  | { type: "manual-fee-selected"; number: string; feeIndex: number; lieu?: string | null }
  // Back to what a saved claim kept (see manualCodesFromClaim) — not a change by the physician.
  | { type: "manual-codes-restored"; manual: ManualCodesState };

export function isManualCodesAction(action: { type: string }): action is ManualCodesAction {
  return action.type.startsWith("manual-");
}

export function manualCodesReducer(state: ManualCodesState, action: ManualCodesAction): ManualCodesState {
  switch (action.type) {
    case "manual-code-added":
      if (state.codes.some((c) => c.number === action.hit.number)) return state;
      return { ...state, codes: [...state.codes, action.hit] };
    case "manual-code-removed": {
      const feeSelection = new Map(state.feeSelection);
      const lieuSelection = new Map(state.lieuSelection);
      feeSelection.delete(action.number);
      lieuSelection.delete(action.number);
      return { codes: state.codes.filter((c) => c.number !== action.number), feeSelection, lieuSelection };
    }
    case "manual-fee-selected": {
      const feeSelection = new Map(state.feeSelection);
      feeSelection.set(action.number, action.feeIndex);
      const lieuSelection = new Map(state.lieuSelection);
      if (action.lieu) lieuSelection.set(action.number, action.lieu);
      else lieuSelection.delete(action.number);
      return { ...state, feeSelection, lieuSelection };
    }
    case "manual-codes-restored":
      return action.manual;
  }
}

export interface ManualCodeEntry {
  hit: CodeHit;
  feeIndex: number | null;
  fee: ExtractedFee | null;
  lieu: string | null;
}

// Each added code with the fee and lieu it will be billed at.
export function manualEntries(state: ManualCodesState): ManualCodeEntry[] {
  return state.codes.map((hit) => {
    const feeIndex = hit.fees.length > 0 ? (state.feeSelection.get(hit.number) ?? 0) : null;
    const fee = feeIndex != null ? hit.fees[feeIndex] : null;
    const lieu = fee ? (state.lieuSelection.get(hit.number) ?? defaultLieu(fee)) : null;
    return { hit, feeIndex, fee, lieu };
  });
}

export function manualSelectedCodes(state: ManualCodesState): SelectedCode[] {
  return manualEntries(state).map((e) => ({ code: e.hit.number, fee_index: e.feeIndex, lieu: e.lieu ?? undefined }));
}

// A saved claim's added codes, re-read from the codes table (`hits`, which may lack a code
// retired since), with the fee and lieu each was billed at.
export function manualCodesFromClaim(hits: CodeHit[], lines: ClaimCodeLine[]): ManualCodesState {
  const byNumber = new Map(hits.map((hit) => [hit.number, hit]));
  const state: ManualCodesState = { codes: [], feeSelection: new Map(), lieuSelection: new Map() };
  for (const line of lines) {
    const hit = byNumber.get(line.code);
    if (!hit) continue;
    state.codes.push(hit);
    const { feeIndex, lieu } = feeFromClaimLine(hit.fees, line);
    if (feeIndex > 0) state.feeSelection.set(hit.number, feeIndex);
    if (lieu) state.lieuSelection.set(hit.number, lieu);
  }
  return state;
}
