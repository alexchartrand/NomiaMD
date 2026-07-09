import { useEffect, useState } from "react";
import {
  extractBillingCodes,
  getSamplePatient,
  listSamplePatients,
  type ExtractionResult,
  type SamplePatientSummary,
} from "./api";
import { Logo } from "./Logo";

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
    <main className="app-shell">
      <header className="app-header">
        <Logo size={30} />
        <span className="tagline">Billing code extraction — review draft</span>
      </header>

      <p className="lede">
        Paste a transcript below, or load a simulated patient. Codes are suggestions only —
        verify each against the transcript before submitting to RAMQ.
      </p>

      <div className="field-row">
        <label htmlFor="patient-select">Simulated patient:</label>
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
        {patientLoading && <span className="status-inline">Loading...</span>}
        {patientsError && (
          <p className="error-text">Couldn&rsquo;t load patient list: {patientsError}</p>
        )}
      </div>

      <form onSubmit={handleSubmit}>
        <textarea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={12}
          placeholder="Paste the encounter transcript here, or select a simulated patient above..."
        />
        <button type="submit" disabled={loading || !transcript.trim()}>
          {loading ? "Extracting..." : "Extract billing codes"}
        </button>
      </form>

      {error && <p className="error-text">{error}</p>}

      {result && (
        <section className="results">
          <h2>Suggested codes ({result.model})</h2>
          {result.result.notes && <p className="warning-banner">⚠ {result.result.notes}</p>}
          {result.result.codes.length === 0 ? (
            <p>No candidate codes were clearly supported by this transcript.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Description</th>
                  <th>Confidence</th>
                  <th>Price (CAD)</th>
                  <th>Supporting quote</th>
                </tr>
              </thead>
              <tbody>
                {result.result.codes.map((c) => (
                  <tr key={c.code}>
                    <td className="code">{c.code}</td>
                    <td>{c.description}</td>
                    <td>{(c.confidence * 100).toFixed(0)}%</td>
                    <td>{formatPrice(c.price_cad)}</td>
                    <td>
                      <em>&ldquo;{c.supporting_quote}&rdquo;</em>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>
                    <strong>Total</strong>
                  </td>
                  <td>
                    <strong>{formatPrice(result.result.total_price_cad)}</strong>
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          )}
          <p className="footnote">
            Prices are placeholder figures from a development reference table, not real
            RAMQ fees — see the project README.
          </p>
        </section>
      )}
    </main>
  );
}

function formatPrice(priceCad: number | null): string {
  return priceCad === null
    ? "—"
    : priceCad.toLocaleString("en-CA", { style: "currency", currency: "CAD" });
}
