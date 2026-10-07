import type { Claim } from "../../../api";
import { fold } from "../../../utils/text";
import { daysLeft, isAtRisk } from "./deadline";

// "échéance": drafts close to (or past) RAMQ's billing deadline.
export type ClaimStatusFilter = "" | "brouillon" | "échéance" | "soumis";

export interface ClaimFilters {
  status: ClaimStatusFilter;
  source: string;
  patient: string;
}

export const NO_FILTERS: ClaimFilters = { status: "", source: "", patient: "" };

const STATUS_FILTERS: ClaimStatusFilter[] = ["", "brouillon", "échéance", "soumis"];

export function isDeadlineAtRisk(claim: Claim, today: string): boolean {
  return claim.status === "brouillon" && isAtRisk(daysLeft(claim.service_date, today));
}

function matchesStatus(claim: Claim, status: ClaimStatusFilter, today: string): boolean {
  if (status === "échéance") return isDeadlineAtRisk(claim, today);
  return !status || claim.status === status;
}

export function matches(claim: Claim, filters: ClaimFilters, today: string): boolean {
  if (!matchesStatus(claim, filters.status, today)) return false;
  if (filters.source && claim.source_system !== filters.source) return false;
  const query = fold(filters.patient.trim());
  return !query || fold(claim.patient_full_name).includes(query);
}

interface StatusTab {
  id: ClaimStatusFilter;
  label: string;
  // Always listed, even at 0; the others only when they hold something (or are picked).
  core: boolean;
}

const STATUS_TABS: StatusTab[] = [
  { id: "", label: "Toutes", core: true },
  { id: "brouillon", label: "Brouillons", core: true },
  { id: "échéance", label: "Échéance proche", core: false },
  { id: "soumis", label: "Soumises", core: true },
];

// The status tabs with how many claims each holds under the other filters.
export function statusTabs(claims: Claim[], filters: ClaimFilters, today: string) {
  return STATUS_TABS.map((tab) => ({
    id: tab.id,
    label: tab.label,
    count: claims.filter((claim) => matches(claim, { ...filters, status: tab.id }, today)).length,
    core: tab.core,
  })).filter((tab) => tab.core || tab.count > 0 || tab.id === filters.status);
}

// The URL's `status`, `source` and `patient` (an unknown status reads as none).
export function readClaimFilters(params: URLSearchParams): ClaimFilters {
  const status = params.get("status") ?? "";
  return {
    status: (STATUS_FILTERS as string[]).includes(status) ? (status as ClaimStatusFilter) : "",
    source: params.get("source") ?? "",
    patient: params.get("patient") ?? "",
  };
}

export function claimFiltersToParams(filters: ClaimFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (filters.status) params.status = filters.status;
  if (filters.source) params.source = filters.source;
  if (filters.patient) params.patient = filters.patient;
  return params;
}
