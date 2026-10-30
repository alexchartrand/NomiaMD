import type {
  BillingExtractionResponse,
  Claim,
  ClaimCodeLine,
  CodeDetail,
  CodeHit,
  ConsultationDigest,
  Dashboard,
  DashboardKpis,
  DashboardTasks,
  EncounterDetail,
  EncounterPatient,
  EncounterRow,
  EncounterSetting,
  ExtractedCode,
  ExtractedFee,
  Patient,
  Shift,
  ShiftClaim,
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

// `retained` defaults to a high confidence, as the server reads a result stored before it existed.
export function makeProposedCode(overrides: Partial<ExtractedCode> = {}): ExtractedCode {
  return {
    code: "00103",
    description: "Visite principale",
    confidence: "high",
    explanation: "",
    supporting_quote: "",
    needs_confirmation: [],
    fees: [makeFee()],
    retained: (overrides.confidence ?? "high") === "high",
    ...overrides,
  };
}

export function makeDigest(overrides: Partial<ConsultationDigest> = {}): ConsultationDigest {
  return {
    short_description: "Consultation pour une toux depuis trois jours.",
    reason_for_visit: null,
    procedures: [],
    billable_add_ons: [],
    referral: null,
    open_questions: [],
    ...overrides,
  };
}

export function makeExtraction(
  codes: ExtractedCode[],
  overrides: Partial<BillingExtractionResponse> = {},
): BillingExtractionResponse {
  return {
    billing: { codes, notes: null },
    extraction_run_id: 1,
    encounter_date: "2026-10-01",
    encounter_date_raw: null,
    summary: null,
    ...overrides,
  };
}

export function makeClaimLine(overrides: Partial<ClaimCodeLine> = {}): ClaimCodeLine {
  return {
    code: "00103",
    description: "Visite principale",
    origin: "suggested",
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
    encounter_id: null,
    codes: [makeClaimLine()],
    total_amount: 50,
    created_at: "2026-10-01T12:00:00Z",
    updated_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

export function makeCodeHit(overrides: Partial<CodeHit> = {}): CodeHit {
  return {
    number: "00059",
    description: "Suture d'une plaie simple",
    header_path: "C — Actes diagnostiques et thérapeutiques > Peau",
    fees: [makeFee({ amount: 25 })],
    needs_confirmation: [],
    ...overrides,
  };
}

export function makeCodeDetail(overrides: Partial<CodeDetail> = {}): CodeDetail {
  return {
    ...makeCodeHit(),
    when_to_use: [],
    rules: [],
    eligibility: {
      min_age: null,
      max_age: null,
      min_panel_size: null,
      max_panel_size: null,
      requires_registered: null,
      requires_vulnerable: null,
    },
    ...overrides,
  };
}

export function makeShift(overrides: Partial<Shift> = {}): Shift {
  return {
    id: 10,
    series_id: null,
    work_site_id: 1,
    work_site_name: "Urgence Saint-Luc",
    care_setting: "urgence",
    period: "soir",
    service_date: "2026-10-01",
    start_time: "16:00:00",
    end_time: "00:00:00",
    ends_next_day: true,
    day_type: "semaine",
    ...overrides,
  };
}

// A draft claim for a weekday ER evening: 4 h of 09791.
export function makeShiftClaim(overrides: Partial<ShiftClaim> = {}): ShiftClaim {
  return {
    id: 30,
    shift_id: 10,
    service_date: "2026-10-01",
    start_time: "16:00:00",
    end_time: "00:00:00",
    ends_next_day: true,
    care_setting: "urgence",
    period: "soir",
    work_site_name: "Urgence Saint-Luc",
    garde_option: "acte",
    status: "brouillon",
    bill_id: null,
    codes: [
      {
        code: "09791",
        description: "Supplément de garde au service d'urgence — de 20 h à 24 h, du lundi au vendredi",
        origin: "suggested",
        hours: 4,
        hourly_fee: 39.1,
        fee_amount: 156.4,
        secteur_dispensation: "07",
        secteur_dispensation_label: "Service d'urgence",
        source: "P.G. 2.2.9 B, p. 71 (manuel 2026-06-05)",
      },
    ],
    total_amount: 156.4,
    created_at: "2026-10-02T12:00:00Z",
    updated_at: "2026-10-02T12:00:00Z",
    ...overrides,
  };
}

// No shift, no place: nothing is known of where the encounter took place.
export function makeEncounterSetting(overrides: Partial<EncounterSetting> = {}): EncounterSetting {
  return {
    care_setting: null,
    shift: null,
    shift_picked: false,
    needs_shift_choice: false,
    differs_from_run: false,
    shift_options: [],
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
    codes: ["00103"],
    indicative_total: 50,
    extraction_run_id: 1,
    possible_duplicate_ids: [],
    all_clean: false,
    deletable: true,
    setting: makeEncounterSetting(),
    ...overrides,
  };
}

// An empty dashboard on Monday 2026-10-05 unless overridden; `tasks`/`kpis` merge field
// by field, so a test sets only the counts it's about.
export function makeDashboard(
  overrides: Omit<Partial<Dashboard>, "tasks" | "kpis"> & { tasks?: Partial<DashboardTasks>; kpis?: Partial<DashboardKpis> } = {},
): Dashboard {
  const { tasks, kpis, ...rest } = overrides;
  return {
    today: "2026-10-05",
    tasks: {
      to_do: 0,
      to_review: 0,
      approvable: 0,
      to_associate: 0,
      failed: 0,
      extracting: 0,
      possible_duplicates: 0,
      unclaimed_shifts: 0,
      ...tasks,
    },
    kpis: { encounters_this_week: 0, draft_count: 0, draft_total: 0, billed_this_month: 0, ...kpis },
    deadlines: [],
    weekly_activity: Array.from({ length: 8 }, (_, i) => ({
      week_start: new Date(Date.UTC(2026, 7, 17 + 7 * i)).toISOString().slice(0, 10),
      received: 0,
      reviewed: 0,
    })),
    recent_encounters: [],
    ...rest,
  };
}

export function makeEncounterPatient(overrides: Partial<EncounterPatient> = {}): EncounterPatient {
  return {
    id: 1,
    full_name: "Patient Test",
    nam: "TEST12345678",
    date_of_birth: "1980-05-20",
    is_vulnerable: false,
    is_registered: true,
    ...overrides,
  };
}

export function makeEncounterDetail(overrides: Partial<EncounterDetail> = {}): EncounterDetail {
  return {
    id: 1,
    status: "prêt",
    patient: makeEncounterPatient(),
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
    note_scrubbed_at: null,
    extraction_error: null,
    extraction: makeExtraction([makeProposedCode()]),
    claim: null,
    setting: makeEncounterSetting(),
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
