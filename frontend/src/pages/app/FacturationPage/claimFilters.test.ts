import { makeClaim } from "../../../test/factories";
import { claimFiltersToParams, matches, NO_FILTERS, readClaimFilters, statusTabs, type ClaimFilters } from "./claimFilters";

const TODAY = "2026-10-07";

const draft = makeClaim({ id: 1, patient_full_name: "Frédéric Lavoie", service_date: "2026-10-01", source_system: "epic" });
// 80 days old: 10 days left.
const lateDraft = makeClaim({ id: 2, patient_full_name: "Marc Roy", service_date: "2026-07-19", source_system: "manual" });
const submitted = makeClaim({ id: 3, patient_full_name: "Lise Tremblay", status: "soumis", bill_id: 1, service_date: "2026-07-01" });

describe("matches", () => {
  it("keeps every claim with no filter", () => {
    for (const claim of [draft, lateDraft, submitted]) expect(matches(claim, NO_FILTERS, TODAY)).toBe(true);
  });

  it("filters on status, with 'échéance' as the drafts near the deadline", () => {
    const status = (s: ClaimFilters["status"]) => [draft, lateDraft, submitted].filter((c) => matches(c, { ...NO_FILTERS, status: s }, TODAY));
    expect(status("brouillon")).toEqual([draft, lateDraft]);
    expect(status("soumis")).toEqual([submitted]);
    // An old submitted claim is billed already: not at risk.
    expect(status("échéance")).toEqual([lateDraft]);
  });

  it("finds the patient regardless of accents and case", () => {
    expect(matches(draft, { ...NO_FILTERS, patient: "  frederic " }, TODAY)).toBe(true);
    expect(matches(lateDraft, { ...NO_FILTERS, patient: "frederic" }, TODAY)).toBe(false);
  });

  it("filters on the source", () => {
    expect(matches(lateDraft, { ...NO_FILTERS, source: "manual" }, TODAY)).toBe(true);
    expect(matches(draft, { ...NO_FILTERS, source: "manual" }, TODAY)).toBe(false);
  });
});

describe("statusTabs", () => {
  it("counts each status under the other filters, and hides an empty 'échéance'", () => {
    const tabs = statusTabs([draft, lateDraft, submitted], NO_FILTERS, TODAY);
    expect(tabs.map((t) => [t.label, t.count])).toEqual([
      ["Toutes", 3],
      ["Brouillons", 2],
      ["Échéance proche", 1],
      ["Soumises", 1],
    ]);
    expect(statusTabs([draft, submitted], NO_FILTERS, TODAY).map((t) => t.id)).toEqual(["", "brouillon", "soumis"]);
    expect(statusTabs([draft], { ...NO_FILTERS, patient: "marc" }, TODAY).map((t) => t.count)).toEqual([0, 0, 0]);
  });

  it("keeps the picked tab even when it holds nothing", () => {
    expect(statusTabs([draft], { ...NO_FILTERS, status: "échéance" }, TODAY).map((t) => t.id)).toContain("échéance");
  });
});

describe("URL params", () => {
  it("round-trips the filters and ignores an unknown status", () => {
    const filters: ClaimFilters = { status: "échéance", source: "epic", patient: "roy" };
    expect(readClaimFilters(new URLSearchParams(claimFiltersToParams(filters)))).toEqual(filters);
    expect(claimFiltersToParams(NO_FILTERS)).toEqual({});
    expect(readClaimFilters(new URLSearchParams("status=bogus"))).toEqual(NO_FILTERS);
  });
});
