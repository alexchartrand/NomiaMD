import { unwrap } from "./http";

export interface SamplePatientSummary {
  id: string;
  label: string;
}

export interface SamplePatientDetail extends SamplePatientSummary {
  transcript: string;
}

export async function listSamplePatients(): Promise<SamplePatientSummary[]> {
  return unwrap<SamplePatientSummary[]>(await fetch("/api/sample-patients"));
}

export async function getSamplePatient(id: string): Promise<SamplePatientDetail> {
  return unwrap<SamplePatientDetail>(await fetch(`/api/sample-patients/${encodeURIComponent(id)}`));
}
