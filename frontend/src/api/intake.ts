import { unwrap } from "./http";
import type { CareSetting } from "./shifts";

// Mirrors app/intake/models.py's ReceiveOutcomeOut: one received note's fate.
export interface ReceiveOutcome {
  // app/intake/deduplicator.py's DedupOutcome.
  outcome: "new" | "duplicate" | "new_version";
  // The stored encounter; for a duplicate, the one already on file.
  encounter_id: number;
  patient_id: number | null;
  enqueued: boolean;
}

// One note, or a whole ER shift the server splits into one note per `**NAM :**` header.
export interface PastedNotesInput {
  text: string;
  batch_label?: string | null;
  // Where every note took place, when no shift is picked; null = unknown.
  care_setting?: CareSetting | null;
  // The shift every note was written during; it wins over care_setting.
  shift_id?: number | null;
}

// What a paste or an upload says of all its notes alike.
export interface BatchFacts {
  batch_label: string | null;
  care_setting: CareSetting | null;
  shift_id: number | null;
}

// Each note's extraction runs before this returns (inline until the background worker
// exists), so a shift of several notes takes a while.
export async function pushNotes(payload: PastedNotesInput): Promise<ReceiveOutcome[]> {
  const response = await fetch("/api/intake/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<ReceiveOutcome[]>(response);
}

export async function uploadNotes(file: File, facts: BatchFacts): Promise<ReceiveOutcome[]> {
  const body = new FormData();
  body.append("file", file);
  if (facts.batch_label) body.append("batch_label", facts.batch_label);
  if (facts.care_setting) body.append("care_setting", facts.care_setting);
  if (facts.shift_id !== null) body.append("shift_id", String(facts.shift_id));
  return unwrap<ReceiveOutcome[]>(
    await fetch("/api/intake/upload", { method: "POST", credentials: "same-origin", body }),
  );
}

// Mirrors app/intake/models.py's EpicSandboxStatus.
export interface EpicSandboxStatus {
  // How many sandbox patients the import reads.
  patients: number;
}

// The Epic sandbox demo (step 11b) is off unless the backend's EPIC_SANDBOX_ENABLED is on;
// its routes are then a 404, which means "don't show it" here rather than an error.
export async function getEpicSandboxStatus(): Promise<EpicSandboxStatus | null> {
  const response = await fetch("/api/intake/epic-sandbox", { credentials: "same-origin" });
  if (response.status === 404) return null;
  return unwrap<EpicSandboxStatus>(response);
}

// Pulls every sandbox patient's signed notes into the inbox; extraction runs inline, so
// this takes a while. Importing again comes back as duplicates.
export async function importEpicSandboxNotes(): Promise<ReceiveOutcome[]> {
  return unwrap<ReceiveOutcome[]>(
    await fetch("/api/intake/epic-sandbox/import", { method: "POST", credentials: "same-origin" }),
  );
}
