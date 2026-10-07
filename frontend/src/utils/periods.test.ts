import { periodToParams, presetOf, presetPeriod, PRESETS, readPeriodParams } from "./periods";

// Mid-day UTC so the Montreal date is the same calendar day.
function today(iso: string) {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(`${iso}T16:00:00Z`));
}

afterEach(() => vi.useRealTimers());

describe("presetPeriod", () => {
  it("today is a single day", () => {
    today("2026-10-07");
    expect(presetPeriod("today")).toEqual({ date_from: "2026-10-07", date_to: "2026-10-07" });
  });

  it("this week runs Monday to Sunday", () => {
    today("2026-10-07"); // Wednesday
    expect(presetPeriod("this-week")).toEqual({ date_from: "2026-10-05", date_to: "2026-10-11" });
  });

  it.each([
    ["2026-10-05", "2026-10-05", "2026-10-11"], // Monday
    ["2026-10-11", "2026-10-05", "2026-10-11"], // Sunday still belongs to that week
  ])("this week on %s", (now, from, to) => {
    today(now);
    expect(presetPeriod("this-week")).toEqual({ date_from: from, date_to: to });
  });

  it("last week is the previous Monday to Sunday, across a year boundary", () => {
    today("2026-01-02"); // Friday
    expect(presetPeriod("last-week")).toEqual({ date_from: "2025-12-22", date_to: "2025-12-28" });
  });

  it.each([
    ["2026-10-15", "2026-10-01", "2026-10-31"],
    ["2026-02-10", "2026-02-01", "2026-02-28"],
    ["2028-02-10", "2028-02-01", "2028-02-29"],
    ["2026-12-31", "2026-12-01", "2026-12-31"],
    ["2026-01-01", "2026-01-01", "2026-01-31"],
  ])("this month on %s", (now, from, to) => {
    today(now);
    expect(presetPeriod("this-month")).toEqual({ date_from: from, date_to: to });
  });

  it("all has no bounds", () => {
    expect(presetPeriod("all")).toEqual({});
  });
});

describe("presetOf", () => {
  it("round-trips every preset", () => {
    today("2026-10-07");
    for (const preset of PRESETS) {
      expect(presetOf(presetPeriod(preset.id))).toBe(preset.id);
    }
  });

  it("returns null for custom dates", () => {
    today("2026-10-07");
    expect(presetOf({ date_from: "2026-10-02", date_to: "2026-10-03" })).toBeNull();
  });

  it("treats a missing and an undefined bound alike", () => {
    expect(presetOf({ date_from: undefined, date_to: undefined })).toBe("all");
  });
});

describe("period URL params", () => {
  it("no params is the page's default preset", () => {
    today("2026-10-07");
    expect(readPeriodParams(new URLSearchParams(), "today")).toEqual(presetPeriod("today"));
    expect(readPeriodParams(new URLSearchParams(), "all")).toEqual({});
  });

  it("round-trips a date range and 'all'", () => {
    const range = { date_from: "2026-10-01", date_to: "2026-10-03" };
    expect(readPeriodParams(new URLSearchParams(periodToParams(range)), "today")).toEqual(range);
    expect(periodToParams({})).toEqual({ all: "1" });
    expect(readPeriodParams(new URLSearchParams(periodToParams({})), "today")).toEqual({});
  });
});
