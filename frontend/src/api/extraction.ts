import { unwrap } from "./http";
import type { Gender } from "./patients";

export interface ExtractedFee {
  amount: number | null;
  when_to_use: string | null;
  majoration: string | null;
}

export interface ExtractedCode {
  code: string;
  description: string;
  confidence: number;
  supporting_quote: string;
  fee: ExtractedFee;
}

export interface BillingCodesResult {
  codes: ExtractedCode[];
  notes: string | null;
}

export interface ExtractionResult {
  task: string;
  result: BillingCodesResult;
  model: string;
  created_at: string;
}

export interface PatientSuggestionExtracted {
  name_as_stated: string | null;
  ramq_number_as_stated: string | null;
  suggested_full_name: string | null;
  suggested_ramq_number: string | null;
  suggested_date_of_birth: string | null; // ISO date (YYYY-MM-DD)
  date_of_birth_is_estimated: boolean;
  suggested_gender: Gender | null;
  age_years: number | null;
}

export interface PatientSuggestion {
  extracted: PatientSuggestionExtracted | null;
  matched_patient_id: number | null;
}

export interface BillingExtractionResponse {
  billing: ExtractionResult;
  summary_extraction_record_id: number;
  billing_extraction_record_id: number;
  encounter_date: string | null; // ISO date (YYYY-MM-DD)
  encounter_date_raw: string | null;
  patient_suggestion: PatientSuggestion | null;
}

export async function extractBillingCodes(transcript: string, source: string): Promise<BillingExtractionResponse> {
  const response = await fetch("/api/extract", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, task: "billing_codes", source: { system: source } }),
  });
  return unwrap<BillingExtractionResponse>(response);
}
