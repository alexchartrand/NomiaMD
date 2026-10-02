import { extractErrorDetail, unwrap, unwrapVoid } from "./http";
import type { ConfidenceLevel, ExtractedFee } from "./extraction";

// Kept in sync by hand with app/claims/status.py's ClaimStatus. Derived server-side, never
// set: a claim is "soumis" exactly when it's on a bill (bill_id != null) — it only leaves
// "brouillon" via POST /bills (see api/bills.ts) and returns when that bill is deleted.
export const CLAIM_STATUSES = ["brouillon", "soumis"] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

export interface ClaimCodeLine {
  code: string;
  description: string;
  confidence: ConfidenceLevel;
  explanation: string;
  // Dollars only — a fee in "unités" carries its count in fee_units and no fee_amount.
  fee_amount: number | null;
  fee_unit: ExtractedFee["unit"] | null;
  fee_units: number | null;
  fee_role: number | null;
  fee_context: string | null;
  fee_lieux: string[] | null;
  majoration: string | null;
  manual_rev: string | null;
}

export interface Claim {
  id: number;
  patient_id: number;
  patient_full_name: string;
  service_date: string; // ISO date (YYYY-MM-DD)
  status: ClaimStatus;
  bill_id: number | null;
  source_system: string | null;
  codes: ClaimCodeLine[];
  total_amount: number | null;
  created_at: string;
  updated_at: string;
}

export interface SelectedCode {
  code: string;
  // Index into that code's resolved ExtractedFee[] (see api/extraction.ts) — null defaults
  // to the first (and, for a single-fee code, only) entry server-side.
  fee_index: number | null;
}

// No patient or source: both come from the extraction run server-side, since its codes were
// eligibility-filtered for that run's patient.
export interface ClaimInput {
  extraction_run_id: number;
  service_date: string;
  selected_codes: SelectedCode[];
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
  return sendClaim("/api/claims", "POST", payload, confirmDuplicate);
}

// A changed review of a draft: the server voids `id` and returns the claim saved in its place
// (a new id). Refused (409) once the claim is on a bill.
export async function replaceClaim(id: number, payload: ClaimInput, confirmDuplicate = false): Promise<Claim> {
  return sendClaim(`/api/claims/${id}`, "PUT", payload, confirmDuplicate);
}

async function sendClaim(url: string, method: "POST" | "PUT", payload: ClaimInput, confirmDuplicate: boolean): Promise<Claim> {
  const response = await fetch(`${url}?confirm_duplicate=${confirmDuplicate}`, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  // Only a "duplicate_claim" 409 is a warning the physician may override; another 409 (an
  // encounter confirmed as another's duplicate, a claim already on a bill) is a plain refusal.
  if (response.status === 409) {
    const body = await response.json().catch(() => null);
    const detail = (body as { detail?: { code?: unknown; message?: unknown } } | null)?.detail;
    if (detail && typeof detail === "object" && detail.code === "duplicate_claim") {
      throw new DuplicateClaimError(
        typeof detail.message === "string" ? detail.message : "Une facturation existe déjà pour ce patient à cette date.",
      );
    }
    throw new Error(extractErrorDetail(body, "La facturation a été refusée."));
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

// Voids the claim server-side (it stays on record, hidden from lists). Only a draft can be
// deleted; status is otherwise read-only, see CLAIM_STATUSES' comment above.
export async function deleteClaim(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/claims/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
