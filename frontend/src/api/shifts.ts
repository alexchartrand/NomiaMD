import { unwrap, unwrapVoid } from "./http";

// Kept in sync by hand with SITE_CARE_SETTINGS in backend/app/shifts/models.py.
export const SITE_CARE_SETTINGS = [
  { value: "urgence", label: "Urgence" },
  { value: "hospitalisation", label: "Hospitalisation" },
  { value: "chsld", label: "CHSLD" },
  { value: "gmf", label: "GMF" },
] as const;
export type SiteCareSetting = (typeof SITE_CARE_SETTINGS)[number]["value"];

// Kept in sync by hand with app/care_setting.py's CareSetting.
export type CareSetting = SiteCareSetting | "cabinet" | "domicile";

export const CARE_SETTING_LABELS: Record<CareSetting, string> = {
  urgence: "Urgence",
  hospitalisation: "Hospitalisation",
  chsld: "CHSLD",
  gmf: "GMF",
  cabinet: "Cabinet",
  domicile: "Domicile",
};

// Kept in sync by hand with app/shifts/periods.py's ShiftPeriod.
export const SHIFT_PERIODS = [
  { value: "jour", label: "Jour" },
  { value: "soir", label: "Soir" },
  { value: "nuit", label: "Nuit" },
] as const;
export type ShiftPeriod = (typeof SHIFT_PERIODS)[number]["value"];

// Kept in sync by hand with app/shifts/day_type.py's DayType.
export type DayType = "semaine" | "fin_de_semaine" | "ferie";

export interface WorkSite {
  id: number;
  name: string;
  care_setting: SiteCareSetting;
  etablissement_number: string | null;
  is_active: boolean;
}

export interface WorkSiteInput {
  name: string;
  care_setting: SiteCareSetting;
  etablissement_number: string | null;
}

export interface Shift {
  id: number;
  work_site_id: number;
  work_site_name: string;
  care_setting: CareSetting;
  period: ShiftPeriod;
  service_date: string; // YYYY-MM-DD, the day the shift starts
  start_time: string; // HH:MM:SS, clinic local time
  end_time: string; // at or before start_time: the next day
  ends_next_day: boolean;
  day_type: DayType;
}

export interface ShiftInput {
  work_site_id: number;
  period: ShiftPeriod;
  service_date: string;
  start_time: string;
  end_time: string;
}

// One shift a day from start_date to end_date (both included), same site and hours.
export interface ShiftSeriesInput {
  work_site_id: number;
  period: ShiftPeriod;
  start_date: string;
  end_date: string;
  start_time: string;
  end_time: string;
  weekdays_only: boolean;
}

export interface PeriodDefault {
  period: ShiftPeriod;
  label: string;
  start_time: string;
  end_time: string;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export async function listWorkSites(includeInactive = false): Promise<WorkSite[]> {
  const query = includeInactive ? "?include_inactive=true" : "";
  return unwrap<WorkSite[]>(await fetch(`/api/work-sites${query}`, { credentials: "same-origin" }));
}

export async function createWorkSite(payload: WorkSiteInput): Promise<WorkSite> {
  return unwrap<WorkSite>(
    await fetch("/api/work-sites", {
      method: "POST",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateWorkSite(id: number, payload: WorkSiteInput): Promise<WorkSite> {
  return unwrap<WorkSite>(
    await fetch(`/api/work-sites/${id}`, {
      method: "PUT",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  );
}

export async function setWorkSiteActive(id: number, active: boolean): Promise<WorkSite> {
  const action = active ? "reactivate" : "deactivate";
  return unwrap<WorkSite>(
    await fetch(`/api/work-sites/${id}/${action}`, { method: "POST", credentials: "same-origin" }),
  );
}

export async function listShifts(start: string, end: string): Promise<Shift[]> {
  const params = new URLSearchParams({ start, end });
  return unwrap<Shift[]>(await fetch(`/api/shifts?${params}`, { credentials: "same-origin" }));
}

export async function listPeriodDefaults(): Promise<PeriodDefault[]> {
  return unwrap<PeriodDefault[]>(await fetch("/api/shifts/periods", { credentials: "same-origin" }));
}

export async function createShift(payload: ShiftInput): Promise<Shift> {
  return unwrap<Shift>(
    await fetch("/api/shifts", {
      method: "POST",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  );
}

export async function createShiftSeries(payload: ShiftSeriesInput): Promise<Shift[]> {
  return unwrap<Shift[]>(
    await fetch("/api/shifts/series", {
      method: "POST",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  );
}

export async function updateShift(id: number, payload: ShiftInput): Promise<Shift> {
  return unwrap<Shift>(
    await fetch(`/api/shifts/${id}`, {
      method: "PUT",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    }),
  );
}

export async function deleteShift(id: number): Promise<void> {
  return unwrapVoid(await fetch(`/api/shifts/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
