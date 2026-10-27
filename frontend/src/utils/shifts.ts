import { CARE_SETTING_LABELS, SHIFT_PERIODS, type Shift } from "../api";
import { addDays, clinicDayOf } from "./date";

const PERIOD_LABELS = Object.fromEntries(SHIFT_PERIODS.map((p) => [p.value, p.label]));

// "mar. 27 oct."
function shortDay(isoDate: string): string {
  return new Intl.DateTimeFormat("fr-CA", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(`${isoDate}T00:00:00Z`));
}

// "Urgence soir" — what kind of shift, without where or when.
export function shiftKind(shift: Shift): string {
  return `${CARE_SETTING_LABELS[shift.care_setting]} ${PERIOD_LABELS[shift.period].toLowerCase()}`;
}

// "Urgence soir, mar. 27 oct. · Hôpital Test (16:00–00:00)" — one shift among others to pick from.
export function shiftLabel(shift: Shift): string {
  const hours = `${shift.start_time.slice(0, 5)}–${shift.end_time.slice(0, 5)}`;
  return `${shiftKind(shift)}, ${shortDay(shift.service_date)} · ${shift.work_site_name} (${hours})`;
}

// A shift's start and end as sortable "YYYY-MM-DDTHH:MM" strings, in clinic local time.
function bounds(shift: Shift): [string, string] {
  const endDay = shift.ends_next_day ? addDays(shift.service_date, 1) : shift.service_date;
  return [`${shift.service_date}T${shift.start_time.slice(0, 5)}`, `${endDay}T${shift.end_time.slice(0, 5)}`];
}

// The clinic's "now" as "YYYY-MM-DDTHH:MM".
export function clinicNow(date: Date = new Date()): string {
  const time = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Montreal",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return `${clinicDayOf(date.toISOString())}T${time}`;
}

// What a paste most likely comes from: the shift under way, else the latest one already
// started (the night just finished) — null when none has.
export function likelyShift(shifts: Shift[], now: string): Shift | null {
  const started = shifts.filter((shift) => bounds(shift)[0] <= now);
  const current = started.find((shift) => now < bounds(shift)[1]);
  if (current) return current;
  return started.reduce<Shift | null>((latest, shift) => (!latest || bounds(shift)[0] > bounds(latest)[0] ? shift : latest), null);
}
