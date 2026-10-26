import type { UserRole } from "../../../api";

const DATE_TIME = new Intl.DateTimeFormat("fr-CA", {
  timeZone: "America/Montreal",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

// An ISO timestamp as the clinic reads it: "2026-10-19 14 h 32".
export function formatDateTime(isoTimestamp: string | null): string {
  return isoTimestamp ? DATE_TIME.format(new Date(isoTimestamp)) : "—";
}

const INTEGER = new Intl.NumberFormat("fr-CA");

export function formatCount(value: number): string {
  return INTEGER.format(value);
}

// Estimated USD (the API sends a Decimal string). Small amounts keep their cents' fractions:
// one extraction costs well under a cent.
export function formatUsd(value: string | null): string {
  if (value === null) return "—";
  const amount = Number(value);
  return new Intl.NumberFormat("fr-CA", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: amount !== 0 && Math.abs(amount) < 1 ? 4 : 2,
  }).format(amount);
}

export function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrateur",
  physician: "Médecin",
};

// Kept in sync by hand with AuditAction in backend/app/audit/actions.py.
export const AUDIT_ACTION_LABELS: Record<string, string> = {
  "user.created": "Compte créé",
  "user.updated": "Compte modifié",
  "user.role_changed": "Rôle modifié",
  "user.deactivated": "Compte désactivé",
  "user.reactivated": "Compte réactivé",
  "user.password_reset": "Mot de passe réinitialisé",
  "user.sessions_revoked": "Sessions fermées",
  "login.succeeded": "Connexion",
  "login.failed": "Connexion refusée",
  "login.unlocked": "Connexion déverrouillée",
  "password.changed": "Mot de passe changé",
  "extraction.retried": "Extraction relancée",
};

// Kept in sync by hand with the pipeline steps' NAMEs (ConsultationSummarizer, CodeSelector…).
export const PURPOSE_LABELS: Record<string, string> = {
  consultation_summary: "Résumé de la consultation",
  billing_codes: "Choix des codes",
  "billing_codes.retrieval": "Recherche des codes",
  ramq_chatbot: "Assistant RAMQ",
  "ramq_chatbot.retrieval": "Recherche de l'assistant",
};
