import { unwrap } from "./http";

// A candidate's real fee entry, resolved server-side after the LLM call — the model never
// picks a fee (see CLAUDE.md's billing_codes architecture note); the physician picks among
// these in the review UI when a code has more than one.
export interface ExtractedFee {
  amount: number | null;
  amount_text: string | null;
  context: string | null;
  lieu: string | null;
  majoration: string | null;
}

export type ConfidenceLevel = "high" | "medium" | "low";

export interface ExtractedCode {
  code: string;
  description: string;
  confidence: ConfidenceLevel;
  explanation: string;
  supporting_quote: string;
  needs_confirmation: string[];
  fees: ExtractedFee[];
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

export interface BillingExtractionResponse {
  billing: ExtractionResult;
  summary_extraction_record_id: number;
  billing_extraction_record_id: number;
  encounter_date: string | null; // ISO date (YYYY-MM-DD)
  encounter_date_raw: string | null;
}

export async function extractBillingCodes(
  transcript: string,
  source: string,
  patientId: number,
): Promise<BillingExtractionResponse> {
  const response = await fetch("/api/extract", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, task: "billing_codes", patient_id: patientId, source: { system: source } }),
  });
  return unwrap<BillingExtractionResponse>(response);
}
