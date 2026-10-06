import { useEffect, useMemo, useReducer } from "react";
import {
  createClaim,
  describeError,
  DuplicateClaimError,
  getCode,
  replaceClaim,
  type BillingExtractionResponse,
  type Claim,
  type CodeHit,
} from "../../../api";
import { initialReviewState, reviewReducer } from "./reviewState";
import { defaultLieu, feeTotals } from "./feeOptions";
import { manualCodesFromClaim, manualEntries, manualSelectedCodes } from "./manualCodes";

export interface CodeReviewOptions {
  // Shown, never saved: already billed, an outdated version, or a confirmed duplicate.
  readOnly?: boolean;
  // The one already saved from this encounter, whose codes, fees and date start selected;
  // saving replaces it.
  claim?: Claim | null;
  // Called once the claim is saved.
  onSaved?: () => void;
  // Asked when the server finds a claim for the same patient and day: the server's message
  // in, whether to save anyway out.
  confirmDuplicate: (message: string) => Promise<boolean>;
}

// One extraction's review, from the codes the physician ticks to the saved claim. A new
// `result` (another encounter, a re-run) resets everything derived from the previous one.
export function useCodeReview(
  result: BillingExtractionResponse | null,
  { readOnly = false, claim = null, onSaved, confirmDuplicate }: CodeReviewOptions,
) {
  const [state, dispatch] = useReducer(reviewReducer, initialReviewState);

  // A review that can't be saved shows nothing ticked beyond its claim's codes. The codes the
  // claim added by hand are re-read from the codes table for their fee options.
  useEffect(() => {
    dispatch(result ? { type: "extracted", result, claim, preselect: !readOnly } : { type: "cleared" });
    const added = result ? (claim?.codes.filter((line) => line.origin === "manual") ?? []) : [];
    if (added.length === 0) return;
    let current = true;
    Promise.allSettled(added.map((line) => getCode(line.code))).then((outcomes) => {
      if (!current) return;
      const hits = outcomes.flatMap((o): CodeHit[] => (o.status === "fulfilled" ? [o.value] : []));
      dispatch({ type: "manual-codes-restored", manual: manualCodesFromClaim(hits, added) });
    });
    return () => {
      current = false;
    };
  }, [result, claim, readOnly]);

  const selectedEntries = useMemo(() => {
    const { result, selection, feeSelection, lieuSelection } = state;
    if (!result) return [];
    return [...selection]
      .sort((a, b) => a - b)
      .map((i) => {
        const code = result.billing.result.codes[i];
        const feeIndex = code.fees.length > 0 ? (feeSelection.get(i) ?? 0) : null;
        const fee = feeIndex != null ? code.fees[feeIndex] : null;
        const lieu = fee ? (lieuSelection.get(i) ?? defaultLieu(fee)) : null;
        return { code, feeIndex, fee, lieu };
      });
  }, [state]);

  const addedEntries = useMemo(() => manualEntries(state.manual), [state.manual]);
  const { totalAmount, codesMissingFee } = feeTotals([...selectedEntries, ...addedEntries].map((e) => e.fee));
  const hasCodes = state.selection.size > 0 || state.manual.codes.length > 0;
  const canSave = !readOnly && Boolean(state.serviceDate) && hasCodes && (claim === null || !state.pristine);

  // Resolves true once the claim is saved.
  async function save(overrideDuplicate = false): Promise<boolean> {
    const { result, serviceDate } = state;
    if (!result || !serviceDate || !hasCodes || readOnly) return false;
    dispatch({ type: "save-started" });
    try {
      const selectedCodes = new Map(selectedEntries.map((e) => [e.code.code, { code: e.code.code, fee_index: e.feeIndex, lieu: e.lieu ?? undefined }]));
      const payload = {
        extraction_run_id: result.extraction_run_id,
        service_date: serviceDate,
        selected_codes: [...selectedCodes.values(), ...manualSelectedCodes(state.manual)],
      };
      await (claim ? replaceClaim(claim.id, payload, overrideDuplicate) : createClaim(payload, overrideDuplicate));
      dispatch({ type: "save-succeeded" });
      onSaved?.();
      return true;
    } catch (err) {
      // Only offer the confirm-and-retry dance on the first attempt: re-submitting the
      // exact same extraction (as opposed to the same patient/date via a different one) is
      // never overridable server-side, so retrying with confirm_duplicate=true would 409
      // again forever. Surfacing it as a plain error here breaks that loop.
      if (err instanceof DuplicateClaimError && !overrideDuplicate) {
        if (await confirmDuplicate(err.message)) return save(true);
        dispatch({ type: "save-cancelled" });
        return false;
      }
      dispatch({ type: "save-failed", error: describeError(err) });
      return false;
    }
  }

  return {
    state,
    readOnly,
    // Saving replaces an existing claim rather than creating one.
    editing: claim !== null,
    toggleCode: (index: number) => dispatch({ type: "code-toggled", index }),
    selectFee: (index: number, feeIndex: number, lieu: string | null = null) =>
      dispatch({ type: "fee-selected", index, feeIndex, lieu }),
    changeServiceDate: (date: string) => dispatch({ type: "service-date-changed", date }),
    addCode: (hit: CodeHit) => dispatch({ type: "manual-code-added", hit }),
    removeCode: (number: string) => dispatch({ type: "manual-code-removed", number }),
    selectAddedFee: (number: string, feeIndex: number, lieu: string | null = null) =>
      dispatch({ type: "manual-fee-selected", number, feeIndex, lieu }),
    totalAmount,
    codesMissingFee,
    canSave,
    save: () => save(false),
  };
}

export type CodeReview = ReturnType<typeof useCodeReview>;
