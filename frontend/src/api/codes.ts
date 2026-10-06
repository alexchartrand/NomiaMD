import { unwrap } from "./http";
import type { ExtractedFee } from "./extraction";

// Kept in sync by hand with backend/app/code_catalog/models.py. A hit's `fees` keep the codes
// table's order: a fee's position is the `fee_index` a claim is saved with (see SelectedCode).
export interface CodeHit {
  number: string;
  description: string;
  // The manual's taxonomy path, e.g. "B — Consultation, examen et visite > Visites …".
  header_path: string;
  fees: ExtractedFee[];
  // The eligibility axes this code is bound on that the patient's facts can't resolve, in
  // French — empty when the search wasn't for a patient.
  needs_confirmation: string[];
}

// Inclusive, whole units; null means no restriction on that axis.
export interface CodeEligibility {
  min_age: number | null;
  max_age: number | null;
  min_panel_size: number | null;
  max_panel_size: number | null;
  requires_registered: boolean | null;
  requires_vulnerable: boolean | null;
}

export interface CodeDetail extends CodeHit {
  when_to_use: string[];
  rules: string[];
  eligibility: CodeEligibility;
}

export interface CodeSearchParams {
  // A code number (or its first digits) or words of its description; empty = the
  // physician's most billed codes.
  q?: string;
  // With a patient, only the codes that patient may be billed on serviceDate (today when
  // omitted) come back.
  patientId?: number | null;
  serviceDate?: string | null;
  limit?: number;
}

export async function searchCodes({ q, patientId, serviceDate, limit }: CodeSearchParams = {}): Promise<CodeHit[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (patientId != null) params.set("patient_id", String(patientId));
  if (serviceDate) params.set("service_date", serviceDate);
  if (limit != null) params.set("limit", String(limit));
  const query = params.toString();
  return unwrap<CodeHit[]>(await fetch(`/api/codes/search${query ? `?${query}` : ""}`, { credentials: "same-origin" }));
}

export async function getCode(number: string): Promise<CodeDetail> {
  return unwrap<CodeDetail>(await fetch(`/api/codes/${encodeURIComponent(number)}`, { credentials: "same-origin" }));
}
