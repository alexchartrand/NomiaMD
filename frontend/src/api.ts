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

// A network-level fetch failure (server unreachable, connection reset) surfaces as a
// TypeError with an opaque browser message ("Failed to fetch") rather than an HTTP error.
export function describeError(err: unknown): string {
  if (err instanceof TypeError) {
    return "Impossible de joindre le serveur. Vérifiez que le serveur est démarré, puis réessayez.";
  }
  return err instanceof Error ? err.message : String(err);
}

export async function extractBillingCodes(transcript: string): Promise<ExtractionResult> {
  const response = await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, task: "billing_codes" }),
  });
  return unwrap<ExtractionResult>(response);
}

export async function listSamplePatients(): Promise<SamplePatientSummary[]> {
  return unwrap<SamplePatientSummary[]>(await fetch("/api/patients"));
}

export async function getSamplePatient(id: string): Promise<SamplePatientDetail> {
  return unwrap<SamplePatientDetail>(await fetch(`/api/patients/${encodeURIComponent(id)}`));
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

export async function login(email: string, password: string): Promise<UserOut> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password } satisfies LoginRequest),
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
  const response = await fetch("/api/auth/me/password", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(extractErrorDetail(body, `La requête a échoué : ${response.status}`));
  }
}
