import { unwrap, unwrapVoid } from "./http";

// Kept in sync by hand with Gender in backend/app/postgresdb/models.py.
export const GENDERS = ["M", "F", "Autre"] as const;
export type Gender = (typeof GENDERS)[number];

// A single identity per NAM, shared across every physician — not owned by any one of
// them. `is_registered_with_current_physician` is read-only and request-relative:
// computed server-side from the requesting physician's own practice_number, never sent on
// create/update.
export interface Patient {
  id: number;
  full_name: string;
  ramq_number: string | null;
  date_of_birth: string; // ISO date (YYYY-MM-DD)
  gender: Gender | null;
  is_vulnerable: boolean;
  family_doctor_name: string | null;
  family_doctor_practice_number: string | null;
  is_registered_with_current_physician: boolean | null;
}

export type PatientInput = Omit<Patient, "id" | "is_registered_with_current_physician">;

// A physician's own optional "my patients" list — membership plus a personal note,
// layered on top of the shared Patient identity above.
export interface RosterEntry extends Patient {
  notes: string | null;
}

export interface RosterEntryInput {
  patient_id: number;
  notes?: string | null;
}

export async function listRoster(): Promise<RosterEntry[]> {
  return unwrap<RosterEntry[]>(await fetch("/api/patients", { credentials: "same-origin" }));
}

export async function searchPatients(query: string): Promise<Patient[]> {
  const params = new URLSearchParams({ q: query });
  return unwrap<Patient[]>(
    await fetch(`/api/patients/search?${params.toString()}`, { credentials: "same-origin" }),
  );
}

export async function getPatient(id: number): Promise<Patient> {
  return unwrap<Patient>(await fetch(`/api/patients/${id}`, { credentials: "same-origin" }));
}

export async function createPatient(payload: PatientInput): Promise<Patient> {
  const response = await fetch("/api/patients", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<Patient>(response);
}

// Edits the shared patient record — admin-only server-side (see app/patients/router.py).
export async function updatePatient(id: number, payload: PatientInput): Promise<Patient> {
  const response = await fetch(`/api/patients/${id}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<Patient>(response);
}

export async function addToRoster(payload: RosterEntryInput): Promise<RosterEntry> {
  const response = await fetch("/api/patients/roster", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<RosterEntry>(response);
}

export async function updateRosterEntry(patientId: number, notes: string | null): Promise<RosterEntry> {
  const response = await fetch(`/api/patients/roster/${patientId}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  return unwrap<RosterEntry>(response);
}

export async function removeFromRoster(patientId: number): Promise<void> {
  await unwrapVoid(
    await fetch(`/api/patients/roster/${patientId}`, { method: "DELETE", credentials: "same-origin" }),
  );
}
