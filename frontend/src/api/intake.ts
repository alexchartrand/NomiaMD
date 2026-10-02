import { unwrap } from "./http";

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

export async function uploadNotes(file: File, batchLabel: string | null): Promise<ReceiveOutcome[]> {
  const body = new FormData();
  body.append("file", file);
  if (batchLabel) body.append("batch_label", batchLabel);
  return unwrap<ReceiveOutcome[]>(
    await fetch("/api/intake/upload", { method: "POST", credentials: "same-origin", body }),
  );
}
