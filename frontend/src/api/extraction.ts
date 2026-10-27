import { unwrap } from "./http";
import type { CareSetting, DayType, ShiftPeriod } from "./shifts";

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

export interface ReferralDigest {
  requester: string | null;
  reason: string | null;
}

// The consultation summary as the review shows it above the codes.
export interface ConsultationDigest {
  short_description: string;
  reason_for_visit: string | null;
  procedures: string[];
  billable_add_ons: string[];
  // Only an incoming referral: another professional asked this physician to see the patient.
  referral: ReferralDigest | null;
  // What the summary couldn't settle, phrased as questions for the physician.
  open_questions: string[];
}

// Where the run took the encounter to be (app/extraction/models.py's RunSettingOut); each
// null when unknown.
export interface RunSetting {
  care_setting: CareSetting | null;
  shift_id: number | null;
  shift_period: ShiftPeriod | null;
  day_type: DayType | null;
}

export interface BillingExtractionResponse {
  billing: BillingCodesResult;
  // What POST /claims takes — the run carries the patient and both stages' results.
  extraction_run_id: number;
  encounter_date: string | null; // ISO date (YYYY-MM-DD)
  encounter_date_raw: string | null;
  // Null for a run whose summary is missing or was stored under an older schema.
  summary?: ConsultationDigest | null;
  // The setting the codes were chosen under, as the run stored it; absent in POST /extract's own response.
  setting?: RunSetting | null;
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
    body: JSON.stringify({ transcript, patient_id: patientId, source: { system: source } }),
  });
  return unwrap<BillingExtractionResponse>(response);
}
