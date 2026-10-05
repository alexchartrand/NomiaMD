import { describe, expect, it } from "vitest";
import { buildFeeOptions, defaultLieu } from "./feeOptions";
import { makeFee } from "../../../test/factories";

describe("buildFeeOptions", () => {
  it("splits a fee listing several lieux into one option per lieu", () => {
    const options = buildFeeOptions([makeFee({ lieux: ["cabinet", "domicile"] })]);
    expect(options.map((o) => [o.feeIndex, o.lieu, o.label])).toEqual([
      [0, "cabinet", "cabinet"],
      [0, "domicile", "domicile"],
    ]);
  });

  it("labels a fee without lieux 'Autre'", () => {
    expect(buildFeeOptions([makeFee({ lieux: [] })]).map((o) => o.label)).toEqual(["Autre"]);
  });

  it("tells options sharing a lieu apart by role", () => {
    const options = buildFeeOptions([
      makeFee({ lieux: ["cabinet"], role: 1 }),
      makeFee({ lieux: ["cabinet"], role: 2 }),
    ]);
    expect(options.map((o) => o.label)).toEqual(["cabinet — R = 1", "cabinet — R = 2"]);
  });
});

describe("defaultLieu", () => {
  it("is the first lieu of a fee listing several, else null", () => {
    expect(defaultLieu(makeFee({ lieux: ["cabinet", "domicile"] }))).toBe("cabinet");
    expect(defaultLieu(makeFee({ lieux: ["cabinet"] }))).toBeNull();
  });
});
