import { unwrap, unwrapVoid } from "./http";

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
