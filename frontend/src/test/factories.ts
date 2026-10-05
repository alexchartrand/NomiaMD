import type {
  BillingExtractionResponse,
  Claim,
  ClaimCodeLine,
  EncounterDetail,
  EncounterRow,
  ExtractedCode,
  ExtractedFee,
  Patient,
} from "../api";

// Synthetic fixtures only (no real NAMs or names). Typed against src/api so a drift in the
// backend contract surfaces in `tsc -b` as well as in the tests.

export function makeFee(overrides: Partial<ExtractedFee> = {}): ExtractedFee {
  return {
    amount: 50,
    amount_text: null,
    role: null,
    unit: "dollars",
    context: null,
    lieux: [],
    majoration: null,
    ...overrides,
  };
}

export function makeProposedCode(overrides: Partial<ExtractedCode> = {}): ExtractedCode {
  return {
    code: "00103",
    description: "Visite principale",
    confidence: "high",
    explanation: "",
    supporting_quote: "",
    needs_confirmation: [],
    fees: [makeFee()],
    ...overrides,
  };
}

export function makeExtraction(
  codes: ExtractedCode[],
  overrides: Partial<BillingExtractionResponse> = {},
): BillingExtractionResponse {
  return {
    billing: {
      task: "billing_codes",
      result: { codes, notes: null },
      model: "test-model",
      created_at: "2026-10-01T12:00:00Z",
    },
    extraction_run_id: 1,
    encounter_date: "2026-10-01",
    encounter_date_raw: null,
    ...overrides,
  };
}

export function makeClaimLine(overrides: Partial<ClaimCodeLine> = {}): ClaimCodeLine {
  return {
    code: "00103",
    description: "Visite principale",
    confidence: "high",
    explanation: "",
    fee_amount: 50,
    fee_unit: "dollars",
    fee_units: null,
    fee_role: null,
    fee_context: null,
    fee_lieux: null,
    majoration: null,
    manual_rev: null,
    ...overrides,
  };
}

export function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    id: 1,
    patient_id: 1,
    patient_full_name: "Patient Test",
    service_date: "2026-10-01",
    status: "brouillon",
    bill_id: null,
    source_system: null,
    codes: [makeClaimLine()],
    total_amount: 50,
    created_at: "2026-10-01T12:00:00Z",
    updated_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

export function makeEncounterRow(overrides: Partial<EncounterRow> = {}): EncounterRow {
  return {
    id: 1,
    status: "prêt",
    patient: { id: 1, display_name: "Frédéric T.", nam: "TEST ******01" },
    source_system: "sample",
    channel: "paste",
    batch_label: null,
    service_date: "2026-10-01",
    received_at: "2026-10-01T12:00:00Z",
    code_count: 1,
    extraction_run_id: 1,
    possible_duplicate_ids: [],
    all_clean: false,
    deletable: true,
    ...overrides,
  };
}

export function makeEncounterDetail(overrides: Partial<EncounterDetail> = {}): EncounterDetail {
  return {
    id: 1,
    status: "prêt",
    patient: { id: 1, full_name: "Patient Test", nam: "TEST12345678" },
    source_system: "sample",
    channel: "paste",
    external_note_id: null,
    external_encounter_id: null,
    batch_label: null,
    service_date: "2026-10-01",
    received_at: "2026-10-01T12:00:00Z",
    meta: {},
    duplicate_of_id: null,
    note_text: "Note de test.",
    extraction_error: null,
    extraction: makeExtraction([makeProposedCode()]),
    claim: null,
    ...overrides,
  };
}

export function makePatient(overrides: Partial<Patient> = {}): Patient {
  return {
    id: 1,
    full_name: "Patient Test",
    ramq_number: "TEST12345678",
    date_of_birth: "1980-05-01",
    gender: null,
    is_vulnerable: false,
    family_doctor_name: null,
    family_doctor_practice_number: null,
    is_registered_with_current_physician: null,
    ...overrides,
  };
}
