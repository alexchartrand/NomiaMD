import { unwrap, unwrapVoid } from "./http";
import type { Claim } from "./claims";
import type { BillingExtractionResponse } from "./extraction";

// Kept in sync by hand with app/intake/status.py's EncounterStatus. Derived server-side,
// never set — see that module for which rule wins when several hold.
export const ENCOUNTER_STATUSES = ["reçu", "prêt", "revu", "modifié", "échec", "à associer"] as const;
export type EncounterStatus = (typeof ENCOUNTER_STATUSES)[number];

// The rest of this file mirrors app/encounters/models.py.

// Enough to recognize the patient in a list seen over a shoulder ("Roch D.", NAM with its
// birth-date digits hidden); the detail has the full identity.
export interface MaskedPatient {
  id: number;
  display_name: string;
  nam: string | null;
}

export interface EncounterPatient {
  id: number;
  full_name: string;
  nam: string | null;
  // What the billing context reads from the patient's file; registration derived against
  // the signed-in physician, null when either practice number is missing.
  date_of_birth: string; // ISO date (YYYY-MM-DD)
  is_vulnerable: boolean;
  is_registered: boolean | null;
}

export interface EncounterRow {
  id: number;
  status: EncounterStatus;
  patient: MaskedPatient | null;
  source_system: string;
  channel: string;
  batch_label: string | null;
  service_date: string | null; // ISO date (YYYY-MM-DD)
  received_at: string;
  // How many codes its live claim bills once there is one (status "revu"), else how many the
  // latest run proposes; null when never extracted.
  code_count: number | null;
  // The codes shown: the claim's, else the latest run's high-confidence ones (what the
  // review starts with ticked). The total is theirs, indicative; null when none has a
  // dollar fee.
  codes: string[] | null;
  indicative_total: number | null;
  // The latest run (what POST /claims takes); null when never extracted.
  extraction_run_id: number | null;
  // "Doublon possible": the other encounters this may be the same visit as, until the
  // physician answers (confirmDuplicate / dismissDuplicate below).
  possible_duplicate_ids: number[];
  // Approvable from the list without opening it — the rule lives server-side
  // (app/encounters/readiness.py), never here.
  all_clean: boolean;
  // No live claim, so DELETE /encounters/:id will be accepted.
  deletable: boolean;
}

export interface EncounterDetail {
  id: number;
  status: EncounterStatus;
  patient: EncounterPatient | null;
  source_system: string;
  channel: string;
  external_note_id: string | null;
  external_encounter_id: string | null;
  batch_label: string | null;
  service_date: string | null;
  received_at: string;
  // Source facts (time_start, time_end, location_label, author_ref...), see EncounterMeta.
  meta: Record<string, string | null>;
  duplicate_of_id: number | null;
  note_text: string;
  extraction_error: string | null;
  extraction: BillingExtractionResponse | null;
  // The live claim saved from one of its runs: the codes the physician selected.
  claim: Claim | null;
}

// Service dates from `date_from` through `date_to`, both included (YYYY-MM-DD); either may
// be left out, and neither lists every encounter. An undated encounter counts on the day it
// was received.
export interface EncounterPeriod {
  date_from?: string | null;
  date_to?: string | null;
}

export async function listEncounters(period: EncounterPeriod = {}): Promise<EncounterRow[]> {
  const params = new URLSearchParams();
  if (period.date_from) params.set("date_from", period.date_from);
  if (period.date_to) params.set("date_to", period.date_to);
  const query = params.toString();
  return unwrap<EncounterRow[]>(await fetch(`/api/encounters${query ? `?${query}` : ""}`, { credentials: "same-origin" }));
}

export async function getEncounter(id: number): Promise<EncounterDetail> {
  return unwrap<EncounterDetail>(await fetch(`/api/encounters/${id}`, { credentials: "same-origin" }));
}

// Also queues its extraction — inline until the background worker exists, so this waits on
// the LLM.
export async function assignEncounterPatient(id: number, patientId: number): Promise<EncounterDetail> {
  const response = await fetch(`/api/encounters/${id}/patient`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id: patientId }),
  });
  return unwrap<EncounterDetail>(response);
}

// Runs the extraction now, in the request: a first extraction, a retry after "échec", or a re-run.
export async function extractEncounter(id: number): Promise<BillingExtractionResponse> {
  return unwrap<BillingExtractionResponse>(
    await fetch(`/api/encounters/${id}/extract`, { method: "POST", credentials: "same-origin" }),
  );
}

// Same visit: `id` is hidden from the inbox and its extraction is never billed; `keptId` stays.
export async function confirmDuplicate(id: number, keptId: number): Promise<void> {
  await unwrapVoid(
    await fetch(`/api/encounters/${id}/duplicate-of/${keptId}`, { method: "POST", credentials: "same-origin" }),
  );
}

// Distinct visits: `id` is never flagged again.
export async function dismissDuplicate(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/encounters/${id}/not-duplicate`, { method: "POST", credentials: "same-origin" }));
}

// Removes the encounter and its extractions for good; refused (409) while it has a claim.
export async function deleteEncounter(id: number): Promise<void> {
  await unwrapVoid(await fetch(`/api/encounters/${id}`, { method: "DELETE", credentials: "same-origin" }));
}
