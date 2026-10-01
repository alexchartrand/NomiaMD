import { useEffect, useMemo, useReducer } from "react";
import { createClaim, describeError, DuplicateClaimError, type BillingExtractionResponse, type ExtractedFee } from "../../../api";
import { initialReviewState, reviewReducer } from "./reviewState";

// A fee in "unités" is a count of anesthesia base units, not a price — it never adds to the
// dollar total, and counts as a code without a dollar amount.
const dollarAmount = (fee: ExtractedFee | null) => (fee?.unit === "dollars" ? fee.amount : null);

// One extraction's review, from the codes the physician ticks to the saved claim. A new
// `result` (another encounter, a re-run) resets everything derived from the previous one.
// `readOnly`: shown, never saved — already billed, an outdated version, or a confirmed duplicate.
export function useCodeReview(result: BillingExtractionResponse | null, readOnly = false) {
  const [state, dispatch] = useReducer(reviewReducer, initialReviewState);

  useEffect(() => {
    dispatch(result ? { type: "extracted", result } : { type: "cleared" });
  }, [result]);

  const selectedEntries = useMemo(() => {
    const { result, selection, feeSelection } = state;
    if (!result) return [];
    return [...selection]
      .sort((a, b) => a - b)
      .map((i) => {
        const code = result.billing.result.codes[i];
        const feeIndex = code.fees.length > 0 ? (feeSelection.get(i) ?? 0) : null;
        const fee = feeIndex != null ? code.fees[feeIndex] : null;
        return { code, feeIndex, fee };
      });
  }, [state]);

  const totalAmount = selectedEntries.reduce((sum, e) => sum + (dollarAmount(e.fee) ?? 0), 0);
  const codesMissingFee = selectedEntries.filter((e) => dollarAmount(e.fee) == null).length;
  const canSave = !readOnly && Boolean(state.serviceDate) && state.selection.size > 0;

  async function save(confirmDuplicate = false): Promise<void> {
    const { result, serviceDate, selection } = state;
    if (!result || !serviceDate || selection.size === 0 || readOnly) return;
    dispatch({ type: "save-started" });
    try {
      const selectedCodes = new Map(selectedEntries.map((e) => [e.code.code, { code: e.code.code, fee_index: e.feeIndex }]));
      await createClaim(
        {
          extraction_run_id: result.extraction_run_id,
          service_date: serviceDate,
          selected_codes: [...selectedCodes.values()],
        },
        confirmDuplicate,
      );
      dispatch({ type: "save-succeeded" });
    } catch (err) {
      // Only offer the confirm-and-retry dance on the first attempt: re-submitting the
      // exact same extraction (as opposed to the same patient/date via a different one) is
      // never overridable server-side, so retrying with confirmDuplicate=true would 409
      // again forever. Surfacing it as a plain error here breaks that loop.
      if (err instanceof DuplicateClaimError && !confirmDuplicate) {
        if (window.confirm(`${err.message} Enregistrer quand même ?`)) {
          await save(true);
          return;
        }
        dispatch({ type: "save-cancelled" });
        return;
      }
      dispatch({ type: "save-failed", error: describeError(err) });
    }
  }

  return {
    state,
    toggleCode: (index: number) => dispatch({ type: "code-toggled", index }),
    selectFee: (index: number, feeIndex: number) => dispatch({ type: "fee-selected", index, feeIndex }),
    changeServiceDate: (date: string) => dispatch({ type: "service-date-changed", date }),
    totalAmount,
    codesMissingFee,
    canSave,
    save: () => save(false),
  };
}

export type CodeReview = ReturnType<typeof useCodeReview>;
