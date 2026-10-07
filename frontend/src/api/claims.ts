import { extractErrorDetail, unwrap, unwrapVoid } from "./http";
import type { ConfidenceLevel, ExtractedFee } from "./extraction";
import { fetchAllPages } from "./paging";

// Kept in sync by hand with app/claims/status.py's ClaimStatus. Derived server-side, never
// set: a claim is "soumis" exactly when it's on a bill (bill_id != null) — it only leaves
// "brouillon" via POST /bills (see api/bills.ts) and returns when that bill is deleted.
export const CLAIM_STATUSES = ["brouillon", "soumis"] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

// Kept in sync by hand with backend/app/claims/origin.py's CodeOrigin: "suggested" — offered by
// the claim's extraction; "manual" — added by the physician from the code search.
export type CodeOrigin = "suggested" | "manual";

// Kept in sync with MANUAL_SOURCE_SYSTEM there: the source_system of a claim billed without an
// encounter (no note).
export const MANUAL_SOURCE_SYSTEM = "manual";

export interface ClaimCodeLine {
  code: string;
  description: string;
  origin: CodeOrigin;
  // Null for a code added by hand — it was never scored.
  confidence: ConfidenceLevel | null;
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
  // The encounter it was billed from; null when billed without one or once purged.
  encounter_id: number | null;
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
  // One of that fee's lieux, when it lists several; the claim then keeps only it.
  lieu?: string | null;
}

// No patient or source: both come from the extraction run server-side, since its codes were
// eligibility-filtered for that run's patient. `selected_codes` may hold codes the run didn't
// suggest: the server snapshots those from the codes table, eligibility-checked.
export interface ClaimInput {
  extraction_run_id: number;
  service_date: string;
  selected_codes: SelectedCode[];
}

// A claim billed without an encounter: every code picked from the code search.
export interface ManualClaimInput {
  patient_id: number;
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

export async function createManualClaim(payload: ManualClaimInput): Promise<Claim> {
  return sendManualClaim("/api/claims/manual", "POST", payload);
}

// Same void-and-recreate as replaceClaim, for a draft billed without an encounter.
export async function replaceManualClaim(id: number, payload: ManualClaimInput): Promise<Claim> {
  return sendManualClaim(`/api/claims/manual/${id}`, "PUT", payload);
}

async function sendManualClaim(url: string, method: "POST" | "PUT", payload: ManualClaimInput): Promise<Claim> {
  return unwrap<Claim>(
    await fetch(url, {
      method,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}

export async function getClaim(id: number): Promise<Claim> {
  return unwrap<Claim>(await fetch(`/api/claims/${id}`, { credentials: "same-origin" }));
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

// Every claim matching the filters (a page's `limit`/`offset` are this function's business).
export function listAllClaims(filters: Omit<ClaimFilters, "limit" | "offset"> = {}): Promise<Claim[]> {
  return fetchAllPages((limit, offset) => listClaims({ ...filters, limit, offset }));
}

// Voids the claim server-side (it stays on record, hidden from lists). Only a draft can be
// deleted; status is otherwise read-only, see CLAIM_STATUSES' comment above.
export async function deleteClaim(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/claims/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
