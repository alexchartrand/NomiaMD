import { PLANS, PRICING_FAQ } from "./pricing";

describe("pricing plans", () => {
  it("has unique ids", () => {
    const ids = PLANS.map((plan) => plan.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("highlights at most one plan", () => {
    expect(PLANS.filter((plan) => plan.highlighted).length).toBeLessThanOrEqual(1);
  });

  it("gives every plan features and a call to action", () => {
    for (const plan of PLANS) {
      expect(plan.features.length).toBeGreaterThan(0);
      expect(plan.cta.label).not.toBe("");
      expect(plan.cta.to).not.toBe("");
    }
  });

  it("has an unit whenever there is a price", () => {
    for (const plan of PLANS.filter((p) => p.price !== null)) {
      expect(plan.unit).not.toBe("");
    }
  });

  it("has a non-empty FAQ", () => {
    for (const entry of PRICING_FAQ) {
      expect(entry.question).not.toBe("");
      expect(entry.answer).not.toBe("");
    }
  });
});
