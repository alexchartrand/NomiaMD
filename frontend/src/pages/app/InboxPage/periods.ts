import type { EncounterPeriod } from "../../../api";
import { addDays, clinicToday, weekdayIndex } from "../../../utils/date";

export type PresetId = "today" | "this-week" | "last-week" | "this-month" | "all";

interface Preset {
  id: PresetId;
  label: string;
  // Relative to the clinic's today, so "cette semaine" moves with the calendar.
  period: (today: string) => EncounterPeriod;
}

// Weeks run Monday through Sunday.
export const PRESETS: Preset[] = [
  { id: "today", label: "Aujourd'hui", period: (today) => ({ date_from: today, date_to: today }) },
  {
    id: "this-week",
    label: "Cette semaine",
    period: (today) => {
      const monday = addDays(today, -weekdayIndex(today));
      return { date_from: monday, date_to: addDays(monday, 6) };
    },
  },
  {
    id: "last-week",
    label: "Semaine dernière",
    period: (today) => {
      const monday = addDays(today, -weekdayIndex(today) - 7);
      return { date_from: monday, date_to: addDays(monday, 6) };
    },
  },
  {
    id: "this-month",
    label: "Ce mois-ci",
    period: (today) => {
      const first = `${today.slice(0, 8)}01`;
      const firstOfNext = `${addDays(first, 32).slice(0, 8)}01`;
      return { date_from: first, date_to: addDays(firstOfNext, -1) };
    },
  },
  { id: "all", label: "Tout", period: () => ({}) },
];

export const DEFAULT_PRESET: PresetId = "this-week";

// Which preset a period is, if it is one (null = custom dates).
export function presetOf(period: EncounterPeriod): PresetId | null {
  const today = clinicToday();
  const match = PRESETS.find((preset) => {
    const candidate = preset.period(today);
    return (candidate.date_from ?? null) === (period.date_from ?? null) && (candidate.date_to ?? null) === (period.date_to ?? null);
  });
  return match?.id ?? null;
}

export function presetPeriod(id: PresetId): EncounterPeriod {
  return PRESETS.find((preset) => preset.id === id)!.period(clinicToday());
}
