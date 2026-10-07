import {
  addDays,
  ageOn,
  clinicDayOf,
  clinicToday,
  daysBetween,
  formatAge,
  formatClinicTime,
  formatDate,
  formatLongDate,
  weekdayIndex,
} from "./date";

afterEach(() => vi.useRealTimers());

describe("formatDate", () => {
  it("renders ISO as DD/MM/YYYY", () => {
    expect(formatDate("2026-03-04")).toBe("04/03/2026");
  });

  it("returns an unparseable value unchanged", () => {
    expect(formatDate("n/a")).toBe("n/a");
  });
});

describe("clinic time zone", () => {
  it("clinicToday follows Montreal, not UTC, late in the evening", () => {
    // 2026-01-16T03:30Z is 22:30 on the 15th in Montreal (EST, UTC-5).
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-16T03:30:00Z"));
    expect(clinicToday()).toBe("2026-01-15");
  });

  it("clinicToday rolls over at Montreal midnight", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-16T05:00:00Z")); // 00:00 EST
    expect(clinicToday()).toBe("2026-01-16");
  });

  it("uses daylight time in summer (UTC-4)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-16T03:30:00Z")); // 23:30 EDT on the 15th
    expect(clinicToday()).toBe("2026-07-15");
    vi.setSystemTime(new Date("2026-07-16T04:00:00Z")); // 00:00 EDT
    expect(clinicToday()).toBe("2026-07-16");
  });

  it("handles the spring-forward day (2026-03-08)", () => {
    expect(clinicDayOf("2026-03-08T06:59:00Z")).toBe("2026-03-08"); // 01:59 EST
    expect(clinicDayOf("2026-03-08T07:00:00Z")).toBe("2026-03-08"); // 03:00 EDT
    expect(clinicDayOf("2026-03-09T03:59:00Z")).toBe("2026-03-08"); // 23:59 EDT
    expect(clinicDayOf("2026-03-09T04:00:00Z")).toBe("2026-03-09");
  });

  it("handles the fall-back day (2026-11-01)", () => {
    expect(clinicDayOf("2026-11-01T03:59:00Z")).toBe("2026-10-31"); // 23:59 EDT
    expect(clinicDayOf("2026-11-01T04:00:00Z")).toBe("2026-11-01"); // 00:00 EDT
    expect(clinicDayOf("2026-11-02T04:59:00Z")).toBe("2026-11-01"); // 23:59 EST
    expect(clinicDayOf("2026-11-02T05:00:00Z")).toBe("2026-11-02");
  });

  it("formatClinicTime shows the Montreal wall clock", () => {
    // fr-CA renders "09 h 05" (spacing varies by ICU version), hence the whitespace strip.
    expect(formatClinicTime("2026-01-15T14:05:00Z").replace(/\s/g, "")).toBe("09h05"); // EST
    expect(formatClinicTime("2026-07-15T14:05:00Z").replace(/\s/g, "")).toBe("10h05"); // EDT
  });
});

describe("addDays", () => {
  it.each([
    ["2026-01-31", 1, "2026-02-01"],
    ["2026-12-31", 1, "2027-01-01"],
    ["2027-01-01", -1, "2026-12-31"],
    ["2028-02-28", 1, "2028-02-29"], // leap year
    ["2026-02-28", 1, "2026-03-01"],
    ["2026-03-07", 2, "2026-03-09"], // across spring-forward
    ["2026-10-31", 2, "2026-11-02"], // across fall-back
    ["2026-05-10", 0, "2026-05-10"],
    ["2026-05-10", -45, "2026-03-26"],
  ])("%s %+d days -> %s", (from, days, expected) => {
    expect(addDays(from, days)).toBe(expected);
  });
});

describe("weekdayIndex", () => {
  it("is Monday = 0 through Sunday = 6", () => {
    expect(weekdayIndex("2026-10-05")).toBe(0); // Monday
    expect(weekdayIndex("2026-10-07")).toBe(2);
    expect(weekdayIndex("2026-10-11")).toBe(6); // Sunday
  });
});

describe("formatLongDate", () => {
  it("spells the date out in French without a time zone shift", () => {
    expect(formatLongDate("2026-03-04")).toBe("mercredi 4 mars 2026");
  });
});

describe("ageOn / formatAge", () => {
  it("counts whole years, the birthday itself included", () => {
    expect(ageOn("1980-05-20", "2026-05-19")).toBe(45);
    expect(ageOn("1980-05-20", "2026-05-20")).toBe(46);
  });

  it("says a toddler's age in months, then years from two", () => {
    expect(formatAge("2024-09-03", "2026-03-03")).toBe("18 mois");
    expect(formatAge("2024-03-03", "2026-03-03")).toBe("2 ans");
    expect(formatAge("1959-01-01", "2026-03-03")).toBe("67 ans");
  });
});

describe("daysBetween", () => {
  it("counts calendar days, across months and backwards", () => {
    expect(daysBetween("2026-10-01", "2026-10-01")).toBe(0);
    expect(daysBetween("2026-09-28", "2026-10-03")).toBe(5);
    expect(daysBetween("2026-10-03", "2026-09-28")).toBe(-5);
  });

  it("isn't thrown off by a daylight-saving change", () => {
    expect(daysBetween("2026-10-31", "2026-11-02")).toBe(2);
  });
});
