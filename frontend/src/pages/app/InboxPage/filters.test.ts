import { makeEncounterRow } from "../../../test/factories";
import { ENCOUNTER_STATUSES } from "../../../api";
import { matches, TO_DO_STATUSES, type RowFilters } from "./filters";

const none: RowFilters = { status: "", source: "", patient: "" };

describe("matches", () => {
  it("accepts every row when no filter is set", () => {
    for (const status of ENCOUNTER_STATUSES) {
      expect(matches(makeEncounterRow({ status }), none)).toBe(true);
    }
  });

  it("'à traiter' keeps what is still to do and drops reviewed or outdated notes", () => {
    const filters: RowFilters = { ...none, status: "à traiter" };
    expect(TO_DO_STATUSES).toEqual(["reçu", "prêt", "à associer", "échec"]);
    for (const status of ENCOUNTER_STATUSES) {
      expect(matches(makeEncounterRow({ status }), filters)).toBe(TO_DO_STATUSES.includes(status));
    }
  });

  it("filters on one exact status", () => {
    expect(matches(makeEncounterRow({ status: "revu" }), { ...none, status: "revu" })).toBe(true);
    expect(matches(makeEncounterRow({ status: "prêt" }), { ...none, status: "revu" })).toBe(false);
  });

  it("filters on the source system", () => {
    const row = makeEncounterRow({ source_system: "epic" });
    expect(matches(row, { ...none, source: "epic" })).toBe(true);
    expect(matches(row, { ...none, source: "plume" })).toBe(false);
  });

  describe("patient search", () => {
    const row = makeEncounterRow({ patient: { id: 1, display_name: "Frédéric T.", nam: "TEST ******01" } });

    it("ignores case and accents", () => {
      expect(matches(row, { ...none, patient: "FRED" })).toBe(true);
      expect(matches(row, { ...none, patient: "frédéric" })).toBe(true);
    });

    it("matches the masked NAM", () => {
      expect(matches(row, { ...none, patient: "test ******01" })).toBe(true);
    });

    it("trims the query and treats a blank one as no filter", () => {
      expect(matches(row, { ...none, patient: "  fred  " })).toBe(true);
      expect(matches(row, { ...none, patient: "   " })).toBe(true);
    });

    it("rejects a non-matching query", () => {
      expect(matches(row, { ...none, patient: "zzz" })).toBe(false);
    });

    it("does not match a row without a patient, unless the query is blank", () => {
      const unassigned = makeEncounterRow({ patient: null });
      expect(matches(unassigned, { ...none, patient: "fred" })).toBe(false);
      expect(matches(unassigned, none)).toBe(true);
    });
  });

  it("combines every filter", () => {
    const row = makeEncounterRow({ status: "prêt", source_system: "epic" });
    expect(matches(row, { status: "prêt", source: "epic", patient: "fred" })).toBe(true);
    expect(matches(row, { status: "prêt", source: "plume", patient: "fred" })).toBe(false);
  });
});
