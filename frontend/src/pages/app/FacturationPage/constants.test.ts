import { makeClaimLine } from "../../../test/factories";
import { describeFee } from "./constants";

describe("describeFee", () => {
  it("is null for a plain dollar fee", () => {
    expect(describeFee(makeClaimLine())).toBeNull();
  });

  it("shows a unit count, never as dollars", () => {
    const line = makeClaimLine({ fee_amount: null, fee_unit: "unités", fee_units: 8 });
    expect(describeFee(line)).toBe("8 unités");
  });

  it("omits the unit count when it is missing", () => {
    expect(describeFee(makeClaimLine({ fee_unit: "unités", fee_units: null }))).toBeNull();
  });

  it("joins role, context and lieux", () => {
    const line = makeClaimLine({ fee_role: 2, fee_context: "soir", fee_lieux: ["cabinet", "domicile"] });
    expect(describeFee(line)).toBe("R = 2 — soir — cabinet, domicile");
  });

  it("keeps a role of 0 (null check, not truthiness)", () => {
    expect(describeFee(makeClaimLine({ fee_role: 0 }))).toBe("R = 0");
  });

  it("skips empty lieux", () => {
    expect(describeFee(makeClaimLine({ fee_lieux: [] }))).toBeNull();
  });
});
