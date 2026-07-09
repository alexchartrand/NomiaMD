import { useEffect, useState } from "react";
import {
  extractBillingCodes,
  getSamplePatient,
  listSamplePatients,
  type ExtractionResult,
  type SamplePatientSummary,
} from "./api";

export default function App() {
  const [transcript, setTranscript] = useState("");
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [patients, setPatients] = useState<SamplePatientSummary[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [patientsError, setPatientsError] = useState<string | null>(null);
  const [patientLoading, setPatientLoading] = useState(false);

  useEffect(() => {
    listSamplePatients()
      .then(setPatients)
      .catch((err) => setPatientsError(err instanceof Error ? err.message : String(err)));
  }, []);

  async function handleSelectPatient(id: string) {
    setSelectedPatientId(id);
    if (!id) return;
    setPatientLoading(true);
    setError(null);
    try {
      const patient = await getSamplePatient(id);
      setTranscript(patient.transcript);
      setResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPatientLoading(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await extractBillingCodes(transcript));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 800, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>NomiaMD — billing code extraction (review draft)</h1>
      <p style={{ color: "#666" }}>
        Paste a transcript below, or load a simulated patient. Codes are suggestions only —
        verify each against the transcript before submitting to RAMQ.
      </p>

      <div style={{ marginBottom: "1rem" }}>
        <label htmlFor="patient-select" style={{ marginRight: "0.5rem" }}>
          Simulated patient:
        </label>
        <select
          id="patient-select"
          value={selectedPatientId}
          onChange={(e) => handleSelectPatient(e.target.value)}
          disabled={patientLoading || patients.length === 0}
        >
          <option value="">
            {patients.length === 0 ? "No simulated patients available" : "Select a patient..."}
          </option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        {patientLoading && <span style={{ marginLeft: "0.5rem" }}>Loading...</span>}
        {patientsError && (
          <p style={{ color: "crimson" }}>Couldn&rsquo;t load patient list: {patientsError}</p>
        )}
      </div>

      <form onSubmit={handleSubmit}>
        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={12}
          style={{ width: "100%", fontFamily: "monospace" }}
          placeholder="Paste the encounter transcript here, or select a simulated patient above..."
        />
        <button type="submit" disabled={loading || !transcript.trim()}>
          {loading ? "Extracting..." : "Extract billing codes"}
        </button>
      </form>

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {result && (
        <section>
          <h2>Suggested codes ({result.model})</h2>
          {result.result.notes && (
            <p style={{ background: "#fff3cd", padding: "0.5rem" }}>
              ⚠ {result.result.notes}
            </p>
          )}
          {result.result.codes.length === 0 ? (
            <p>No candidate codes were clearly supported by this transcript.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={cellStyle}>Code</th>
                  <th style={cellStyle}>Description</th>
                  <th style={cellStyle}>Confidence</th>
                  <th style={cellStyle}>Price (CAD)</th>
                  <th style={cellStyle}>Supporting quote</th>
                </tr>
              </thead>
              <tbody>
                {result.result.codes.map((c) => (
                  <tr key={c.code}>
                    <td style={cellStyle}>{c.code}</td>
                    <td style={cellStyle}>{c.description}</td>
                    <td style={cellStyle}>{(c.confidence * 100).toFixed(0)}%</td>
                    <td style={cellStyle}>{formatPrice(c.price_cad)}</td>
                    <td style={cellStyle}>
                      <em>&ldquo;{c.supporting_quote}&rdquo;</em>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td style={cellStyle} colSpan={3}>
                    <strong>Total</strong>
                  </td>
                  <td style={cellStyle}>
                    <strong>{formatPrice(result.result.total_price_cad)}</strong>
                  </td>
                  <td style={cellStyle} />
                </tr>
              </tfoot>
            </table>
          )}
          <p style={{ color: "#666", fontSize: "0.9em" }}>
            Prices are placeholder figures from a development reference table, not real
            RAMQ fees — see the project README.
          </p>
        </section>
      )}
    </main>
  );
}

const cellStyle: React.CSSProperties = {
  border: "1px solid #ddd",
  padding: "0.5rem",
  textAlign: "left",
};

function formatPrice(priceCad: number | null): string {
  return priceCad === null
    ? "—"
    : priceCad.toLocaleString("en-CA", { style: "currency", currency: "CAD" });
}
