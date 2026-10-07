import type { EncounterPeriod, EncounterRow } from "../../../api";
import { clinicDayOf } from "../../../utils/date";
import { matches, type RowFilters, type StatusFilter } from "./filters";
import { periodToParams, readPeriodParams, type PresetId } from "../../../utils/periods";

export interface DayGroup {
  day: string;
  batches: { label: string | null; rows: EncounterRow[] }[];
}

// The day an encounter belongs to: its service date, or the clinic day it was received on
// while it has none (same rule as the server's period filter).
function dayOf(row: EncounterRow): string {
  return row.service_date ?? clinicDayOf(row.received_at);
}

// Most recent day first; within a day, rows by batch label (an ER shift pasted at once) in
// arrival order, rows with no label forming one unnamed batch.
export function groupByDay(rows: EncounterRow[]): DayGroup[] {
  const days = new Map<string, Map<string | null, EncounterRow[]>>();
  for (const row of rows) {
    const batches =
      days.get(dayOf(row)) ?? new Map<string | null, EncounterRow[]>();
    batches.set(row.batch_label, [
      ...(batches.get(row.batch_label) ?? []),
      row,
    ]);
    days.set(dayOf(row), batches);
  }
  return [...days.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, batches]) => ({
      day,
      batches: [...batches.entries()].map(([label, grouped]) => ({
        label,
        rows: grouped,
      })),
    }));
}

const DEFAULT_PRESET: PresetId = "this-week";

// The URL holds the period and the filters, so the encounter page's "back" (and a reload)
// lands on the same list. No period in the URL is the default preset; `all` is no bounds.
export function readPeriod(params: URLSearchParams): EncounterPeriod {
  return readPeriodParams(params, DEFAULT_PRESET);
}

export function readFilters(params: URLSearchParams): RowFilters {
  return {
    status: (params.get("status") ?? "") as StatusFilter,
    source: params.get("source") ?? "",
    patient: params.get("patient") ?? "",
  };
}

// The list's page, kept in the URL so coming back from an encounter lands on it. Changing
// the period or the filters (`toParams`) leaves it out: back to the first page.
export function readPage(params: URLSearchParams): number {
  return Number(params.get("page")) || 1;
}

export function toParams(
  period: EncounterPeriod,
  filters: RowFilters,
): Record<string, string> {
  const params = periodToParams(period);
  if (filters.status) params.status = filters.status;
  if (filters.source) params.source = filters.source;
  if (filters.patient) params.patient = filters.patient;
  return params;
}

// The inbox as the URL describes it: its period and filters.
export function readView(search: string): {
  period: EncounterPeriod;
  filters: RowFilters;
} {
  const params = new URLSearchParams(search);
  return { period: readPeriod(params), filters: readFilters(params) };
}

// The rows the inbox shows for these filters, in the order it shows them (day, then batch).
export function inboxOrder(
  rows: EncounterRow[],
  filters: RowFilters,
): EncounterRow[] {
  return groupByDay(rows.filter((row) => matches(row, filters))).flatMap(
    (group) => group.batches.flatMap((batch) => batch.rows),
  );
}
