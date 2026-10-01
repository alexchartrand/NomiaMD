import { unwrap } from "./http";

export interface SamplePatientSummary {
  id: string;
  label: string;
}

export interface SamplePatientDetail extends SamplePatientSummary {
  transcript: string;
  // Normalized NAM from the note's header, or null if missing/malformed — used to look up
  // the matching real Patient row (seeded by scripts/seed_db.py) and auto-fill it.
  nam: string | null;
}

export async function listSamplePatients(): Promise<SamplePatientSummary[]> {
  return unwrap<SamplePatientSummary[]>(await fetch("/api/sample-patients"));
}

export async function getSamplePatient(id: string): Promise<SamplePatientDetail> {
  return unwrap<SamplePatientDetail>(await fetch(`/api/sample-patients/${encodeURIComponent(id)}`));
}
