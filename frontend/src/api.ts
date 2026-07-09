export interface ExtractedCode {
  code: string;
  description: string;
  confidence: number;
  supporting_quote: string;
  price_cad: number | null;
}

export interface BillingCodesResult {
  codes: ExtractedCode[];
  notes: string | null;
  total_price_cad: number | null;
}

export interface ExtractionResult {
  task: string;
  result: BillingCodesResult;
  model: string;
  created_at: string;
}

export interface SamplePatientSummary {
  id: string;
  label: string;
}

export interface SamplePatientDetail extends SamplePatientSummary {
  transcript: string;
}

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
  }
  return response.json();
}

export async function extractBillingCodes(transcript: string): Promise<ExtractionResult> {
  const response = await fetch("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, task: "billing_codes" }),
  });
  return unwrap<ExtractionResult>(response);
}

export async function listSamplePatients(): Promise<SamplePatientSummary[]> {
  return unwrap<SamplePatientSummary[]>(await fetch("/api/patients"));
}

export async function getSamplePatient(id: string): Promise<SamplePatientDetail> {
  return unwrap<SamplePatientDetail>(await fetch(`/api/patients/${encodeURIComponent(id)}`));
}
