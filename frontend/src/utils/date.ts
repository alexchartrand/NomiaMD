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

// Calendar arithmetic on YYYY-MM-DD strings, done in UTC so no time zone shifts the day.
export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
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
