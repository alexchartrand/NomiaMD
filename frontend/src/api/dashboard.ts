import type { EncounterRow } from "./encounters";
import { unwrap } from "./http";

// Mirrors backend app/dashboard/models.py by hand.

export interface DashboardTasks {
  to_do: number;
  to_review: number;
  // Of to_review, those approvable from the inbox without opening them (all_clean).
  approvable: number;
  to_associate: number;
  failed: number;
  extracting: number;
  possible_duplicates: number;
}

export interface DashboardKpis {
  encounters_this_week: number;
  draft_count: number;
  draft_total: number;
  billed_this_month: number;
}

// Unbilled work close to (or past) RAMQ's billing deadline.
export interface DeadlineItem {
  kind: "encounter" | "claim";
  id: number;
  patient_display: string | null;
  service_date: string; // ISO date (YYYY-MM-DD)
  // Negative once the deadline has passed.
  days_left: number;
}

export interface WeekActivity {
  week_start: string; // ISO date of the week's Monday
  received: number;
  reviewed: number;
}

export interface Dashboard {
  today: string;
  tasks: DashboardTasks;
  kpis: DashboardKpis;
  deadlines: DeadlineItem[];
  weekly_activity: WeekActivity[];
  recent_encounters: EncounterRow[];
}

export async function getDashboard(): Promise<Dashboard> {
  return unwrap<Dashboard>(await fetch("/api/dashboard", { credentials: "same-origin" }));
}
