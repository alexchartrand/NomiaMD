import type { EncounterRow } from "../../../api";
import { matches, type RowFilters, type StatusFilter } from "./filters";

interface StatusTab {
  id: StatusFilter;
  label: string;
  // Always listed, even at 0; the others only when they hold something (or are picked).
  core: boolean;
}

const STATUS_TABS: StatusTab[] = [
  { id: "", label: "Toutes", core: true },
  { id: "à traiter", label: "À traiter", core: true },
  { id: "prêt", label: "Prêtes", core: true },
  { id: "à associer", label: "À associer", core: false },
  { id: "reçu", label: "En attente", core: false },
  { id: "échec", label: "Échecs", core: false },
  { id: "revu", label: "Revues", core: true },
  { id: "modifié", label: "Modifiées", core: false },
];

// The inbox's status tabs with how many rows each holds under the other filters.
export function statusTabs(rows: EncounterRow[], filters: RowFilters) {
  return STATUS_TABS.map((tab) => ({
    id: tab.id,
    label: tab.label,
    core: tab.core,
    count: rows.filter((row) => matches(row, { ...filters, status: tab.id })).length,
  })).filter((tab) => tab.core || tab.count > 0 || tab.id === filters.status);
}
