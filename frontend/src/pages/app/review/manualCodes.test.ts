import { makeClaimLine, makeCodeHit, makeFee } from "../../../test/factories";
import {
  emptyManualCodes,
  manualCodesFromClaim,
  manualCodesReducer,
  manualEntries,
  manualSelectedCodes,
} from "./manualCodes";

const suture = makeCodeHit();
const visit = makeCodeHit({
  number: "15801",
  fees: [makeFee({ amount: 52.4, role: 1 }), makeFee({ amount: 61.1, role: 2, lieux: ["cabinet", "domicile"] })],
});

describe("manualCodesReducer", () => {
  it("adds a code once, with its first fee by default", () => {
    let state = manualCodesReducer(emptyManualCodes, { type: "manual-code-added", hit: visit });
    state = manualCodesReducer(state, { type: "manual-code-added", hit: visit });
    expect(state.codes).toEqual([visit]);
    expect(manualSelectedCodes(state)).toEqual([{ code: "15801", fee_index: 0, lieu: undefined }]);
  });

  it("bills the chosen fee at the chosen lieu, and forgets both when the code is removed", () => {
    let state = manualCodesReducer(emptyManualCodes, { type: "manual-code-added", hit: visit });
    state = manualCodesReducer(state, { type: "manual-code-added", hit: suture });
    state = manualCodesReducer(state, { type: "manual-fee-selected", number: "15801", feeIndex: 1, lieu: "domicile" });
    expect(manualEntries(state).map((e) => [e.hit.number, e.fee?.amount, e.lieu])).toEqual([
      ["15801", 61.1, "domicile"],
      ["00059", 25, null],
    ]);

    state = manualCodesReducer(state, { type: "manual-code-removed", number: "15801" });
    expect(state.codes).toEqual([suture]);
    expect(state.feeSelection.has("15801")).toBe(false);
    expect(state.lieuSelection.has("15801")).toBe(false);
  });

  it("defaults to a fee's first lieu when it lists several", () => {
    let state = manualCodesReducer(emptyManualCodes, { type: "manual-code-added", hit: visit });
    state = manualCodesReducer(state, { type: "manual-fee-selected", number: "15801", feeIndex: 1 });
    expect(manualEntries(state)[0].lieu).toBe("cabinet");
  });
});

describe("manualCodesFromClaim", () => {
  it("restores each code with the fee and lieu the claim was billed at", () => {
    const lines = [
      makeClaimLine({ code: "15801", origin: "manual", fee_amount: 61.1, fee_role: 2, fee_lieux: ["domicile"] }),
      makeClaimLine({ code: "00059", origin: "manual", fee_amount: 25, fee_role: null }),
    ];
    const state = manualCodesFromClaim([suture, visit], lines);
    expect(state.codes.map((c) => c.number)).toEqual(["15801", "00059"]);
    expect(manualSelectedCodes(state)).toEqual([
      { code: "15801", fee_index: 1, lieu: "domicile" },
      { code: "00059", fee_index: 0, lieu: undefined },
    ]);
  });

  it("leaves out a code the codes table no longer has", () => {
    const state = manualCodesFromClaim([suture], [makeClaimLine({ code: "99999", origin: "manual" })]);
    expect(state.codes).toEqual([]);
  });
});
