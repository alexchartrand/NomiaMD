import { makeClaim, makeClaimLine, makeExtraction, makeFee, makeProposedCode } from "../../../test/factories";
import { initialReviewState, reviewReducer, type ReviewState } from "./reviewState";

const twoFees = makeProposedCode({
  code: "00103",
  fees: [makeFee({ amount: 50, role: 1 }), makeFee({ amount: 70, role: 2, context: "soir" })],
});
const other = makeProposedCode({ code: "15145" });
const result = makeExtraction([twoFees, other]);

describe("reviewReducer", () => {
  it("loads a result with nothing ticked and the encounter date", () => {
    const state = reviewReducer(initialReviewState, { type: "extracted", result });
    expect(state.result).toBe(result);
    expect(state.serviceDate).toBe("2026-10-01");
    expect(state.selection.size).toBe(0);
    expect(state.pristine).toBe(true);
  });

  it("leaves the date empty when the result has none", () => {
    const state = reviewReducer(initialReviewState, {
      type: "extracted",
      result: makeExtraction([], { encounter_date: null }),
    });
    expect(state.serviceDate).toBe("");
  });

  it("starts from the claim's date and ticks its codes, matched by code", () => {
    const claim = makeClaim({ service_date: "2026-09-30", codes: [makeClaimLine({ code: "15145" })] });
    const state = reviewReducer(initialReviewState, { type: "extracted", result, claim });
    expect(state.serviceDate).toBe("2026-09-30");
    expect([...state.selection]).toEqual([1]);
    expect(state.pristine).toBe(true);
  });

  it("selects the fee matching the claim's role, context and amount", () => {
    const claim = makeClaim({
      codes: [makeClaimLine({ code: "00103", fee_amount: 70, fee_role: 2, fee_context: "soir" })],
    });
    const state = reviewReducer(initialReviewState, { type: "extracted", result, claim });
    expect(state.feeSelection.get(0)).toBe(1);
  });

  it("tells fees apart by role alone when amount and context are equal", () => {
    const sameButRole = makeProposedCode({
      code: "00200",
      fees: [makeFee({ amount: 50, role: 1 }), makeFee({ amount: 50, role: 2 })],
    });
    const claim = makeClaim({ codes: [makeClaimLine({ code: "00200", fee_amount: 50, fee_role: 2 })] });
    const state = reviewReducer(initialReviewState, { type: "extracted", result: makeExtraction([sameButRole]), claim });
    expect(state.feeSelection.get(0)).toBe(1);
  });

  it("keeps the default fee when the claimed fee is the first one", () => {
    const claim = makeClaim({ codes: [makeClaimLine({ code: "00103", fee_amount: 50, fee_role: 1 })] });
    const state = reviewReducer(initialReviewState, { type: "extracted", result, claim });
    expect(state.feeSelection.has(0)).toBe(false);
  });

  it("matches a fee in units on fee_units, not fee_amount", () => {
    const anesthesia = makeProposedCode({
      code: "09001",
      fees: [makeFee({ amount: 6, unit: "unités" }), makeFee({ amount: 8, unit: "unités", role: 2 })],
    });
    const claim = makeClaim({
      codes: [makeClaimLine({ code: "09001", fee_amount: null, fee_unit: "unités", fee_units: 8, fee_role: 2 })],
    });
    const state = reviewReducer(initialReviewState, { type: "extracted", result: makeExtraction([anesthesia]), claim });
    expect(state.feeSelection.get(0)).toBe(1);
  });

  it("leaves out a claimed code the result no longer proposes", () => {
    const claim = makeClaim({ codes: [makeClaimLine({ code: "99999" })] });
    const state = reviewReducer(initialReviewState, { type: "extracted", result, claim });
    expect(state.selection.size).toBe(0);
  });

  it("toggles a code and marks the review as changed", () => {
    const loaded = reviewReducer(initialReviewState, { type: "extracted", result });
    const ticked = reviewReducer(loaded, { type: "code-toggled", index: 0 });
    expect(ticked.selection.has(0)).toBe(true);
    expect(ticked.pristine).toBe(false);
    expect(reviewReducer(ticked, { type: "code-toggled", index: 0 }).selection.has(0)).toBe(false);
  });

  it("does not mutate the previous selection", () => {
    const loaded = reviewReducer(initialReviewState, { type: "extracted", result });
    reviewReducer(loaded, { type: "code-toggled", index: 0 });
    reviewReducer(loaded, { type: "fee-selected", index: 0, feeIndex: 1 });
    expect(loaded.selection.size).toBe(0);
    expect(loaded.feeSelection.size).toBe(0);
  });

  it("records a fee choice and a date change as changes", () => {
    const loaded = reviewReducer(initialReviewState, { type: "extracted", result });
    const fee = reviewReducer(loaded, { type: "fee-selected", index: 0, feeIndex: 1 });
    expect(fee.feeSelection.get(0)).toBe(1);
    expect(fee.pristine).toBe(false);
    const date = reviewReducer(loaded, { type: "service-date-changed", date: "2026-10-02" });
    expect(date.serviceDate).toBe("2026-10-02");
    expect(date.pristine).toBe(false);
  });

  it("resets everything when a new result is extracted", () => {
    const dirty: ReviewState = {
      ...reviewReducer(initialReviewState, { type: "extracted", result }),
      selection: new Set([0]),
      pristine: false,
      saved: true,
      saveError: "boom",
    };
    const state = reviewReducer(dirty, { type: "extracted", result: makeExtraction([other]) });
    expect(state.selection.size).toBe(0);
    expect(state.pristine).toBe(true);
    expect(state.saved).toBe(false);
    expect(state.saveError).toBeNull();
  });

  it("clears back to the initial state", () => {
    const loaded = reviewReducer(initialReviewState, { type: "extracted", result });
    expect(reviewReducer(loaded, { type: "cleared" })).toEqual(initialReviewState);
  });

  it("walks through the save outcomes", () => {
    const started = reviewReducer(initialReviewState, { type: "save-started" });
    expect(started.saving).toBe(true);
    expect(reviewReducer(started, { type: "save-succeeded" })).toMatchObject({ saving: false, saved: true });
    expect(reviewReducer(started, { type: "save-cancelled" })).toMatchObject({ saving: false, saved: false });
    expect(reviewReducer(started, { type: "save-failed", error: "non" })).toMatchObject({
      saving: false,
      saveError: "non",
    });
    expect(reviewReducer({ ...started, saveError: "old" }, { type: "save-started" }).saveError).toBeNull();
  });
});
