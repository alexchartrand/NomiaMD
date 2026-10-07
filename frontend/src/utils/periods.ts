import { addDays, clinicToday, weekdayIndex } from "./date";

// A service-date range; either bound may be open. Shaped like the API's Period.
export interface Period {
  date_from?: string | null;
  date_to?: string | null;
}

export type PresetId = "today" | "this-week" | "last-week" | "this-month" | "all";

interface Preset {
  id: PresetId;
  label: string;
  // Relative to the clinic's today, so "cette semaine" moves with the calendar.
  period: (today: string) => Period;
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

// Which preset a period is, if it is one (null = custom dates).
export function presetOf(period: Period): PresetId | null {
  const today = clinicToday();
  const match = PRESETS.find((preset) => {
    const candidate = preset.period(today);
    return (candidate.date_from ?? null) === (period.date_from ?? null) && (candidate.date_to ?? null) === (period.date_to ?? null);
  });
  return match?.id ?? null;
}

export function presetPeriod(id: PresetId): Period {
  return PRESETS.find((preset) => preset.id === id)!.period(clinicToday());
}

// A period as a page's URL holds it: `all=1` for no bounds, else `from`/`to`; neither means
// the page's own default preset.
export function readPeriodParams(params: URLSearchParams, defaultPreset: PresetId): Period {
  if (params.has("all")) return {};
  if (params.has("from") || params.has("to")) return { date_from: params.get("from"), date_to: params.get("to") };
  return presetPeriod(defaultPreset);
}

export function periodToParams(period: Period): Record<string, string> {
  const params: Record<string, string> = {};
  if (!period.date_from && !period.date_to) params.all = "1";
  if (period.date_from) params.from = period.date_from;
  if (period.date_to) params.to = period.date_to;
  return params;
}
