import { unwrap, unwrapVoid } from "./http";

// Kept in sync by hand with Gender in backend/app/postgresdb/models.py.
export const GENDERS = ["M", "F", "Autre"] as const;
export type Gender = (typeof GENDERS)[number];

export interface Patient {
  id: number;
  full_name: string;
  ramq_number: string | null;
  date_of_birth: string; // ISO date (YYYY-MM-DD)
  gender: Gender | null;
  is_registered_with_physician: boolean;
  is_vulnerable: boolean;
}

export type PatientInput = Omit<Patient, "id">;

export async function listPatients(): Promise<Patient[]> {
  return unwrap<Patient[]>(await fetch("/api/patients", { credentials: "same-origin" }));
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

export async function updatePatient(id: number, payload: PatientInput): Promise<Patient> {
  const response = await fetch(`/api/patients/${id}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<Patient>(response);
}

export async function deletePatient(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/patients/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
