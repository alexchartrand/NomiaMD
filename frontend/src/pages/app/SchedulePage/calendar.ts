// Calendar arithmetic for the schedule, on YYYY-MM-DD strings (see utils/date.ts). Weeks
// start on Monday, as in Québec.
import { addDays, weekdayIndex } from "../../../utils/date";

export type CalendarView = "month" | "week";

export const weekStartOf = (day: string) => addDays(day, -weekdayIndex(day));

const monthStartOf = (day: string) => `${day.slice(0, 7)}-01`;

function addMonths(day: string, months: number): string {
  const d = new Date(`${monthStartOf(day)}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + months);
  return d.toISOString().slice(0, 10);
}

export const sameMonth = (a: string, b: string) => a.slice(0, 7) === b.slice(0, 7);

// The days on screen: a week, or the whole weeks spanning `anchor`'s month (4 to 6 of them).
export function visibleDays(view: CalendarView, anchor: string): string[] {
  const first = view === "week" ? weekStartOf(anchor) : weekStartOf(monthStartOf(anchor));
  const last = view === "week" ? addDays(first, 6) : addDays(weekStartOf(addDays(addMonths(anchor, 1), -1)), 6);
  const days = [first];
  while (days[days.length - 1] < last) days.push(addDays(days[days.length - 1], 1));
  return days;
}

// The anchor one week or month before (-1) or after (1).
export function step(view: CalendarView, anchor: string, direction: -1 | 1): string {
  return view === "week" ? addDays(weekStartOf(anchor), 7 * direction) : addMonths(anchor, direction);
}

export function rangeLabel(view: CalendarView, anchor: string): string {
  const at = (day: string) => new Date(`${day}T00:00:00Z`);
  if (view === "month") {
    const label = new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", month: "long", year: "numeric" }).format(at(anchor));
    return label.charAt(0).toUpperCase() + label.slice(1);
  }
  const format = new Intl.DateTimeFormat("fr-CA", { timeZone: "UTC", day: "numeric", month: "long", year: "numeric" });
  return `Semaine du ${format.format(at(weekStartOf(anchor)))}`;
}
