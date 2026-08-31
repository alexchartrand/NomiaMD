import { unwrap, unwrapVoid } from "./http";
import type { ConfidenceLevel } from "./extraction";

// Kept in sync by hand with app/claims/models.py's ClaimStatus Literal. Read-only from
// this API — a claim only leaves "brouillon" via POST /bills (see api/bills.ts), and
// "facture" is reserved for a future real RAMQ submission response; nothing sets it yet.
export const CLAIM_STATUSES = ["brouillon", "soumis", "facture"] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

export interface ClaimCodeLine {
  code: string;
  description: string;
  confidence: ConfidenceLevel;
  explanation: string;
  fee_amount: number | null;
  fee_when_to_use: string | null;
  majoration: string | null;
}

export interface Claim {
  id: number;
  patient_id: number;
  patient_full_name: string;
  service_date: string; // ISO date (YYYY-MM-DD)
  status: ClaimStatus;
  source_system: string | null;
  codes: ClaimCodeLine[];
  total_amount: number | null;
  created_at: string;
  updated_at: string;
}

export interface ClaimInput {
  patient_id: number;
  service_date: string;
  billing_extraction_record_id: number;
  summary_extraction_record_id: number | null;
  selected_codes: string[];
  source_system: string | null;
}

export interface ClaimFilters {
  patient_id?: number;
  date_from?: string;
  date_to?: string;
  status?: ClaimStatus;
  limit?: number;
  offset?: number;
}

export class DuplicateClaimError extends Error {}

export async function createClaim(payload: ClaimInput, confirmDuplicate = false): Promise<Claim> {
  const response = await fetch(`/api/claims?confirm_duplicate=${confirmDuplicate}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 409) {
    const body = await response.json().catch(() => null);
    const detail = (body as { detail?: { message?: unknown } } | null)?.detail;
    const message =
      detail && typeof detail === "object" && typeof detail.message === "string"
        ? detail.message
        : "Une facturation existe déjà pour ce patient à cette date.";
    throw new DuplicateClaimError(message);
  }

  return unwrap<Claim>(response);
}

export async function listClaims(filters: ClaimFilters = {}): Promise<Claim[]> {
  const params = new URLSearchParams();
  if (filters.patient_id != null) params.set("patient_id", String(filters.patient_id));
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.status) params.set("status", filters.status);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const query = params.toString();

  return unwrap<Claim[]>(await fetch(`/api/claims${query ? `?${query}` : ""}`, { credentials: "same-origin" }));
}

// Status is otherwise read-only from this API — there is no PATCH endpoint for it, see
// CLAIM_STATUSES' comment above.
export async function deleteClaim(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/claims/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
