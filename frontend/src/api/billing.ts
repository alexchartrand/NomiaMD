import { unwrap, unwrapVoid } from "./http";

// Kept in sync by hand with app/billing/models.py's BillingStatus Literal. Read-only from
// this API — a record only leaves "brouillon" via POST /bills (see api/bills.ts), and
// "facture" is reserved for a future real RAMQ submission response; nothing sets it yet.
export const BILLING_STATUSES = ["brouillon", "soumis", "facture"] as const;
export type BillingStatus = (typeof BILLING_STATUSES)[number];

export interface BillingCodeLine {
  code: string;
  description: string;
  confidence: number;
  supporting_quote: string;
  fee_amount: number | null;
  fee_when_to_use: string | null;
  majoration: string | null;
}

export interface BillingRecord {
  id: number;
  patient_id: number;
  patient_full_name: string;
  service_date: string; // ISO date (YYYY-MM-DD)
  status: BillingStatus;
  source_system: string | null;
  codes: BillingCodeLine[];
  total_amount: number | null;
  created_at: string;
  updated_at: string;
}

export interface BillingRecordInput {
  patient_id: number;
  service_date: string;
  billing_extraction_record_id: number;
  summary_extraction_record_id: number | null;
  selected_codes: string[];
  source_system: string | null;
}

export interface BillingRecordFilters {
  patient_id?: number;
  date_from?: string;
  date_to?: string;
  status?: BillingStatus;
  limit?: number;
  offset?: number;
}

export class DuplicateBillingRecordError extends Error {}

export async function createBillingRecord(
  payload: BillingRecordInput,
  confirmDuplicate = false,
): Promise<BillingRecord> {
  const response = await fetch(`/api/billing-records?confirm_duplicate=${confirmDuplicate}`, {
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
    throw new DuplicateBillingRecordError(message);
  }

  return unwrap<BillingRecord>(response);
}

export async function listBillingRecords(filters: BillingRecordFilters = {}): Promise<BillingRecord[]> {
  const params = new URLSearchParams();
  if (filters.patient_id != null) params.set("patient_id", String(filters.patient_id));
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.status) params.set("status", filters.status);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  const query = params.toString();

  return unwrap<BillingRecord[]>(
    await fetch(`/api/billing-records${query ? `?${query}` : ""}`, { credentials: "same-origin" }),
  );
}

// Status is otherwise read-only from this API — there is no PATCH endpoint for it, see
// BILLING_STATUSES' comment above.
export async function deleteBillingRecord(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/billing-records/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
