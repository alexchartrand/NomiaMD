import { useEffect, useState } from "react";
import {
  describeError,
  extractBillingCodes,
  getSamplePatient,
  listSamplePatients,
  type ExtractionResult,
  type SamplePatientSummary,
} from "../../api";
import { Banner, Button, Select, Table, TextArea } from "../../components";

export default function ExtractionPage() {
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
      .catch((err) => setPatientsError(describeError(err)));
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
      setError(describeError(err));
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
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page-panel">
      <h1>Extraction de codes</h1>
      <p className="lede">
        Collez une transcription ci-dessous, ou chargez un patient simulé. Les codes sont des
        suggestions seulement — vérifiez chacun par rapport à la transcription avant de
        soumettre à la RAMQ.
      </p>

      <div className="field-row">
        <label htmlFor="patient-select">Patient simulé :</label>
        <Select
          id="patient-select"
          value={selectedPatientId}
          onChange={(e) => handleSelectPatient(e.target.value)}
          disabled={patientLoading || patients.length === 0}
        >
          <option value="">
            {patients.length === 0 ? "Aucun patient simulé disponible" : "Sélectionnez un patient..."}
          </option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </Select>
        {patientLoading && <span className="status-inline">Chargement...</span>}
        {patientsError && (
          <Banner tone="error">Impossible de charger la liste des patients : {patientsError}</Banner>
        )}
      </div>

      <form onSubmit={handleSubmit}>
        <TextArea
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={12}
          placeholder="Collez la transcription de la consultation ici, ou sélectionnez un patient simulé ci-dessus..."
        />
        <Button type="submit" disabled={loading || !transcript.trim()}>
          {loading ? "Extraction en cours..." : "Extraire les codes de facturation"}
        </Button>
      </form>

      {error && <Banner tone="error">{error}</Banner>}

      {result && (
        <section className="results">
          <h2>Codes suggérés ({result.model})</h2>
          {result.result.notes && <Banner tone="warning">⚠ {result.result.notes}</Banner>}
          {result.result.codes.length === 0 ? (
            <p>Aucun code candidat n&rsquo;est clairement appuyé par cette transcription.</p>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Description</th>
                  <th>Confiance</th>
                  <th>Tarif</th>
                  <th>Citation à l&rsquo;appui</th>
                </tr>
              </thead>
              <tbody>
                {result.result.codes.map((c) => (
                  <tr key={c.code}>
                    <td className="code">{c.code}</td>
                    <td>{c.description}</td>
                    <td>{(c.confidence * 100).toFixed(0)}%</td>
                    <td>{c.fee.amount != null ? `${c.fee.amount.toFixed(2)} $` : "—"}</td>
                    <td>
                      <em>&laquo; {c.supporting_quote} &raquo;</em>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </section>
      )}
    </section>
  );
}
