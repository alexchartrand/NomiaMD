import { daysLeft, isAtRisk } from "./deadline";

describe("daysLeft", () => {
  it("counts down 90 days from the service date", () => {
    expect(daysLeft("2026-10-07", "2026-10-07")).toBe(90);
    expect(daysLeft("2026-07-09", "2026-10-07")).toBe(0);
    expect(daysLeft("2026-07-08", "2026-10-07")).toBe(-1);
  });
});

describe("isAtRisk", () => {
  it("warns within the last 15 days, and past the deadline", () => {
    expect(isAtRisk(16)).toBe(false);
    expect(isAtRisk(15)).toBe(true);
    expect(isAtRisk(-3)).toBe(true);
  });
});
