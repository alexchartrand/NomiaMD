// The admin console's API (/admin/*, admins only). Types kept in sync by hand with
// backend/app/admin/models.py.
import { unwrap, unwrapVoid } from "./http";
import type { PhysicianType, RemunerationType } from "./auth";

export type UserRole = "admin" | "physician";

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  must_change_password: boolean;
  practice_number: string | null;
  physician_type: PhysicianType | null;
  panel_size: number | null;
  remuneration_type: RemunerationType | null;
  created_at: string;
  last_login_at: string | null;
  deactivated_at: string | null;
  encounter_count: number;
  claim_count: number;
}

export interface AdminUserFields {
  full_name: string;
  role: UserRole;
  practice_number: string | null;
  physician_type: PhysicianType | null;
  panel_size: number | null;
  remuneration_type: RemunerationType | null;
}

export interface AdminUserCreate extends AdminUserFields {
  email: string;
}

// The temporary password is shown once: it can't be read back later.
export interface TemporaryPassword {
  user: AdminUser;
  temporary_password: string;
}

export type UsageGrouping = "model" | "purpose" | "user";

export interface UsageBucket {
  key: string;
  label: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  // Decimal, serialized as a string; covers priced calls only.
  cost_usd: string;
  unpriced_calls: number;
  errors: number;
  median_latency_ms: number | null;
  p95_latency_ms: number | null;
}

export interface UsageReport {
  start: string;
  end: string;
  totals: UsageBucket;
  extractions: number;
  cost_per_extraction_usd: string | null;
  by_day: UsageBucket[];
  group_by: UsageGrouping;
  breakdown: UsageBucket[];
}

export interface DependencyCheck {
  ok: boolean;
  detail: string;
}

export interface SystemReport {
  checked_at: string;
  app_env: string;
  app_version: string | null;
  database: DependencyCheck;
  codes_table: DependencyCheck;
  models: {
    chat_provider: string;
    embedding_provider: string;
    embedding_model: string | null;
    step_models: Record<string, string>;
  };
  row_counts: Record<string, number>;
  failed_extractions: number;
  // Past retention but not scrubbed yet: the nightly job isn't running if this stays above 0.
  notes_due_for_scrub: number;
  notes_scrubbed: number;
}

export interface FailedExtraction {
  encounter_id: number;
  user_id: number;
  physician_name: string | null;
  source_system: string;
  service_date: string | null;
  received_at: string;
  error: string;
}

export interface Lockout {
  email: string;
  failed_attempts: number;
  last_attempt_at: string;
  locked_until: string | null;
  is_locked: boolean;
  known_account: boolean;
}

export interface ContactRequest {
  id: number;
  created_at: string;
  name: string;
  email: string;
  phone: string | null;
  organization: string | null;
  role: string;
  physician_count: number | null;
  topic: string;
  plan: string | null;
  message: string | null;
}

export interface AuditEvent {
  id: number;
  created_at: string;
  action: string;
  actor_id: number | null;
  actor_name: string | null;
  target_user_id: number | null;
  target_name: string | null;
  details: Record<string, unknown> | null;
  ip: string | null;
}

export interface AuditFilters {
  action?: string;
  user_id?: number;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

function query(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, value]) => value !== undefined && value !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  return unwrap(await fetch("/api/admin/users", { credentials: "same-origin" }));
}

export async function createAdminUser(body: AdminUserCreate): Promise<TemporaryPassword> {
  return unwrap(
    await fetch("/api/admin/users", {
      method: "POST",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  );
}

export async function updateAdminUser(id: number, body: AdminUserFields): Promise<AdminUser> {
  return unwrap(
    await fetch(`/api/admin/users/${id}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }),
  );
}

async function postUserAction<T>(id: number, action: string): Promise<T> {
  return unwrap(await fetch(`/api/admin/users/${id}/${action}`, { method: "POST", credentials: "same-origin" }));
}

export const deactivateAdminUser = (id: number) => postUserAction<AdminUser>(id, "deactivate");
export const reactivateAdminUser = (id: number) => postUserAction<AdminUser>(id, "reactivate");
export const resetAdminUserPassword = (id: number) => postUserAction<TemporaryPassword>(id, "reset-password");

export async function revokeAdminUserSessions(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/admin/users/${id}/revoke-sessions`, { method: "POST", credentials: "same-origin" }));
}

export async function getUsageReport(params: { start?: string; end?: string; group_by: UsageGrouping }): Promise<UsageReport> {
  return unwrap(await fetch(`/api/admin/usage${query(params)}`, { credentials: "same-origin" }));
}

export async function getSystemReport(): Promise<SystemReport> {
  return unwrap(await fetch("/api/admin/system", { credentials: "same-origin" }));
}

export async function listFailedExtractions(): Promise<FailedExtraction[]> {
  return unwrap(await fetch("/api/admin/extraction-failures", { credentials: "same-origin" }));
}

export async function retryExtraction(encounterId: number): Promise<void> {
  await unwrapVoid(
    await fetch(`/api/admin/encounters/${encounterId}/retry`, { method: "POST", credentials: "same-origin" }),
  );
}

export async function listLockouts(): Promise<Lockout[]> {
  return unwrap(await fetch("/api/admin/lockouts", { credentials: "same-origin" }));
}

export async function unlockLogin(email: string): Promise<void> {
  await unwrapVoid(
    await fetch(`/api/admin/lockouts/${encodeURIComponent(email)}`, { method: "DELETE", credentials: "same-origin" }),
  );
}

export async function listContactRequests(limit: number, offset: number): Promise<ContactRequest[]> {
  return unwrap(await fetch(`/api/admin/contact-requests${query({ limit, offset })}`, { credentials: "same-origin" }));
}

export async function listAuditEvents(filters: AuditFilters, limit: number, offset: number): Promise<AuditEvent[]> {
  return unwrap(
    await fetch(`/api/admin/audit${query({ ...filters, limit, offset })}`, { credentials: "same-origin" }),
  );
}
