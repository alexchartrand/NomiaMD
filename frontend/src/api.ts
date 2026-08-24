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

// Kept in sync by hand with Gender in backend/app/postgresdb/models.py.
export const GENDERS = ["M", "F", "Autre"] as const;
export type Gender = (typeof GENDERS)[number];

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

export interface SamplePatientSummary {
  id: string;
  label: string;
}

export interface SamplePatientDetail extends SamplePatientSummary {
  transcript: string;
}

export interface RAMQChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface RAMQQueryResult {
  answer: string;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me: boolean;
}

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  role: "admin" | "physician";
  physician_type: string | null;
  number_of_patients: number | null;
}

// Kept in sync by hand with PhysicianType in backend/app/postgresdb/models.py.
export const PHYSICIAN_TYPES = ["Médecin de famille", "Spécialiste", "Autre"] as const;
export type PhysicianType = (typeof PHYSICIAN_TYPES)[number];

export interface ProfileUpdateRequest {
  full_name: string;
  physician_type: PhysicianType | null;
  number_of_patients: number | null;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

export interface Patient {
  id: number;
  full_name: string;
  ramq_number: string | null;
  date_of_birth: string; // ISO date (YYYY-MM-DD)
  gender: Gender | null;
  is_registered_with_physician: boolean;
  is_vulnerable: boolean;
}

export type PatientInput = Omit<Patient, "id">;

// Kept in sync by hand with app/billing/models.py's BillingStatus Literal.
export const BILLING_STATUSES = ["brouillon", "facture"] as const;
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
}

// FastAPI's `detail` is a plain string for hand-raised HTTPExceptions (401, 400, ...) but a
// list of { msg, loc, type } objects for Pydantic validation errors (422) — stringifying
// that list directly (e.g. via `new Error(detail)`) collapses it to "[object Object]".
function extractErrorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => (entry && typeof entry === "object" && "msg" in entry ? String(entry.msg) : String(entry)))
      .join(" ");
  }
  return fallback;
}

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(extractErrorDetail(body, `La requête a échoué : ${response.status}`));
  }
  return response.json();
}

async function unwrapVoid(response: Response): Promise<void> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(extractErrorDetail(body, `La requête a échoué : ${response.status}`));
  }
}

// A network-level fetch failure (server unreachable, connection reset) surfaces as a
// TypeError with an opaque browser message ("Failed to fetch") rather than an HTTP error.
export function describeError(err: unknown): string {
  if (err instanceof TypeError) {
    return "Impossible de joindre le serveur. Vérifiez que le serveur est démarré, puis réessayez.";
  }
  return err instanceof Error ? err.message : String(err);
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

export async function listSamplePatients(): Promise<SamplePatientSummary[]> {
  return unwrap<SamplePatientSummary[]>(await fetch("/api/sample-patients"));
}

export async function getSamplePatient(id: string): Promise<SamplePatientDetail> {
  return unwrap<SamplePatientDetail>(await fetch(`/api/sample-patients/${encodeURIComponent(id)}`));
}

export async function listPatients(): Promise<Patient[]> {
  return unwrap<Patient[]>(await fetch("/api/patients", { credentials: "same-origin" }));
}

export async function createPatient(payload: PatientInput): Promise<Patient> {
  const response = await fetch("/api/patients", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<Patient>(response);
}

export async function updatePatient(id: number, payload: PatientInput): Promise<Patient> {
  const response = await fetch(`/api/patients/${id}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<Patient>(response);
}

export async function deletePatient(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/patients/${id}`, { method: "DELETE", credentials: "same-origin" }));
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
  const query = params.toString();

  return unwrap<BillingRecord[]>(
    await fetch(`/api/billing-records${query ? `?${query}` : ""}`, { credentials: "same-origin" }),
  );
}

export async function updateBillingRecordStatus(id: number, status: BillingStatus): Promise<BillingRecord> {
  const response = await fetch(`/api/billing-records/${id}`, {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return unwrap<BillingRecord>(response);
}

export async function deleteBillingRecord(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/billing-records/${id}`, { method: "DELETE", credentials: "same-origin" }));
}

export async function queryChatbot(
  query: string,
  history: RAMQChatMessage[],
): Promise<RAMQQueryResult> {
  const response = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history }),
  });
  return unwrap<RAMQQueryResult>(response);
}

export async function login(email: string, password: string, rememberMe: boolean): Promise<UserOut> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, remember_me: rememberMe } satisfies LoginRequest),
  });
  return unwrap<UserOut>(response);
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
}

// Returns null (rather than throwing) when nobody's logged in — that's an expected state
// on first page load, not an error.
export async function getCurrentUser(): Promise<UserOut | null> {
  const response = await fetch("/api/auth/me", { credentials: "same-origin" });
  if (response.status === 401) {
    return null;
  }
  return unwrap<UserOut>(response);
}

export async function updateProfile(payload: ProfileUpdateRequest): Promise<UserOut> {
  const response = await fetch("/api/auth/me", {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<UserOut>(response);
}

export async function changePassword(payload: PasswordChangeRequest): Promise<void> {
  await unwrapVoid(
    await fetch("/api/auth/me/password", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  );
}
