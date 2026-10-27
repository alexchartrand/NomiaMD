import type { ClaimStatus, CodeOrigin } from "./claims";
import { unwrap, unwrapVoid } from "./http";
import type { CareSetting, Shift, ShiftPeriod } from "./shifts";

// Mirrors backend app/shift_claims/models.py by hand.

// A catalog shift code the physician may add, with its hourly fee on the shift's date.
export interface ShiftCode {
  code: string;
  description: string;
  quart_hours: number;
  divisible_in_hours: boolean;
  hourly_fee: number | null;
  // The RAMQ secteur de dispensation it's billed under, e.g. "07" — Service d'urgence.
  secteur_dispensation: string;
  secteur_dispensation_label: string;
  source: string;
}

// A code the shift's rules earned, for the hours they counted.
export interface SuggestedShiftCode {
  code: string;
  description: string;
  hours: number;
  hourly_fee: number | null;
  fee_amount: number | null;
  secteur_dispensation: string;
  secteur_dispensation_label: string;
  source: string;
}

export interface ShiftClaimCode {
  code: string;
  description: string;
  origin: CodeOrigin;
  hours: number;
  hourly_fee: number | null;
  fee_amount: number | null;
  secteur_dispensation: string;
  secteur_dispensation_label: string;
  source: string;
}

// A claim for a shift's own codes: no patient, no NAM. The shift's hours and site are
// snapshotted at save time.
export interface ShiftClaim {
  id: number;
  shift_id: number;
  service_date: string;
  start_time: string;
  end_time: string;
  ends_next_day: boolean;
  care_setting: CareSetting;
  period: ShiftPeriod;
  work_site_name: string;
  status: ClaimStatus;
  bill_id: number | null;
  codes: ShiftClaimCode[];
  total_amount: number | null;
  created_at: string;
  updated_at: string;
}

export interface ShiftBilling {
  shift: Shift;
  suggested: SuggestedShiftCode[];
  available_codes: ShiftCode[];
  claim: ShiftClaim | null;
}

export interface ShiftClaimLine {
  code: string;
  hours: number;
}

export async function getShiftBilling(shiftId: number): Promise<ShiftBilling> {
  return unwrap<ShiftBilling>(await fetch(`/api/shifts/${shiftId}/billing`, { credentials: "same-origin" }));
}

// Creates the shift's claim, or replaces its draft.
export async function saveShiftClaim(shiftId: number, codes: ShiftClaimLine[]): Promise<ShiftClaim> {
  return unwrap<ShiftClaim>(
    await fetch(`/api/shifts/${shiftId}/claim`, {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes }),
    }),
  );
}

export async function listShiftClaims(
  filters: { date_from?: string; date_to?: string; status?: ClaimStatus } = {},
): Promise<ShiftClaim[]> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  const query = params.toString();
  return unwrap<ShiftClaim[]>(await fetch(`/api/shift-claims${query ? `?${query}` : ""}`, { credentials: "same-origin" }));
}

export async function deleteShiftClaim(id: number): Promise<void> {
  return unwrapVoid(await fetch(`/api/shift-claims/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
