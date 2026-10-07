import type { EncounterRow, EncounterStatus } from "../../../api";
import { fold } from "../../../utils/text";

// "à traiter": everything the physician still has to act on — not billed yet, and not an
// outdated version of a note.
export const TO_DO_STATUSES: EncounterStatus[] = ["reçu", "prêt", "à associer", "échec"];

export type StatusFilter = "" | "à traiter" | EncounterStatus;

export interface RowFilters {
  status: StatusFilter;
  source: string;
  // Matches the masked name or NAM the list shows ("Roch D.", "DESR ******01").
  patient: string;
}

export function matches(row: EncounterRow, filters: RowFilters): boolean {
  if (filters.status === "à traiter" && !TO_DO_STATUSES.includes(row.status)) return false;
  if (filters.status && filters.status !== "à traiter" && row.status !== filters.status) return false;
  if (filters.source && row.source_system !== filters.source) return false;
  const query = fold(filters.patient.trim());
  if (query) {
    const haystack = fold(`${row.patient?.display_name ?? ""} ${row.patient?.nam ?? ""}`);
    if (!haystack.includes(query)) return false;
  }
  return true;
}
