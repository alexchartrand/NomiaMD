import { unwrap } from "./http";

// A candidate's real fee entry, resolved server-side after the LLM call — the model never
// picks a fee (see CLAUDE.md's billing_codes architecture note); the physician picks among
// these in the review UI when a code has more than one.
export interface ExtractedFee {
  amount: number | null;
  amount_text: string | null;
  // The manual's raw role column (R = 1, R = 2, R = 7...), null for a single-amount table.
  role: number | null;
  // "unités" means `amount` counts anesthesia base units, not dollars — never billed as $.
  unit: "dollars" | "unités";
  context: string | null;
  lieux: string[];
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
  // The model is sure of it: the review starts with it ticked, and approving from the inbox
  // bills it. The others are only possible codes.
  retained: boolean;
}

export interface BillingCodesResult {
  // Retained codes first, then the other possible ones.
  codes: ExtractedCode[];
  notes: string | null;
  // The model's reasoning before it chose; null for results stored before it existed.
  analysis?: string | null;
}

export interface ExtractionResult {
  task: string;
  result: BillingCodesResult;
  model: string;
  created_at: string;
}

export interface BillingExtractionResponse {
  billing: ExtractionResult;
  // What POST /claims takes — the run carries the patient and both stages' results.
  extraction_run_id: number;
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
