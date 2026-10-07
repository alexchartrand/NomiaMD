// Renders an ISO date (YYYY-MM-DD) in Canadian format (DD/MM/YYYY).
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  if (!year || !month || !day) return isoDate;
  return `${day}/${month}/${year}`;
}

// Today as the clinic sees it (America/Montreal) — the server's own "today" for the inbox,
// whatever the browser's time zone. en-CA formats as YYYY-MM-DD.
export function clinicToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Montreal" }).format(new Date());
}

// The clinic's local time (HH:MM) of an ISO timestamp.
export function formatClinicTime(isoTimestamp: string): string {
  return new Intl.DateTimeFormat("fr-CA", {
    timeZone: "America/Montreal",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoTimestamp));
}

// The clinic's day (YYYY-MM-DD) of an ISO timestamp.
export function clinicDayOf(isoTimestamp: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Montreal" }).format(new Date(isoTimestamp));
}

// Whole years from a birth date to a day (both YYYY-MM-DD): the patient's age at a visit.
export function ageOn(birthDate: string, day: string): number {
  const [by, bm, bd] = birthDate.split("-").map(Number);
  const [y, m, d] = day.split("-").map(Number);
  return y - by - (m < bm || (m === bm && d < bd) ? 1 : 0);
}

// "18 mois" under two years old (how a toddler's age is said, and what a pediatric code
// reads), else "1 an", "67 ans".
export function formatAge(birthDate: string, day: string): string {
  const years = ageOn(birthDate, day);
  if (years >= 2) return `${years} ans`;
  const [by, bm, bd] = birthDate.split("-").map(Number);
  const [y, m, d] = day.split("-").map(Number);
  const months = (y - by) * 12 + (m - bm) - (d < bd ? 1 : 0);
  return `${Math.max(months, 0)} mois`;
}

// Calendar arithmetic on YYYY-MM-DD strings, done in UTC so no time zone shifts the day.
export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// Whole days from `from` to `to` (negative when `to` comes first).
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

// Monday = 0 ... Sunday = 6.
export function weekdayIndex(isoDate: string): number {
  return (new Date(`${isoDate}T00:00:00Z`).getUTCDay() + 6) % 7;
}

// "mercredi 4 mars 2026".
export function formatLongDate(isoDate: string): string {
  return new Intl.DateTimeFormat("fr-CA", {
    timeZone: "UTC",
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(`${isoDate}T00:00:00Z`));
}
