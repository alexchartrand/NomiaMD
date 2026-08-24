import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  GENDERS,
  createBillingRecord,
  createPatient,
  describeError,
  DuplicateBillingRecordError,
  extractBillingCodes,
  getSamplePatient,
  listPatients,
  listSamplePatients,
  type BillingRecordInput,
  type BillingExtractionResponse,
  type Gender,
  type Patient,
  type PatientInput,
  type SamplePatientSummary,
} from "../../api";
import { Banner, Button, Card, Select, Table, TextArea, TextField } from "../../components";

const BLANK_CREATE_FORM = {
  full_name: "",
  ramq_number: "",
  date_of_birth: "",
  gender: null as Gender | null,
};

export default function ExtractionPage() {
  const [source, setSource] = useState<"simule" | null>(null);

  const [transcript, setTranscript] = useState("");
  const [result, setResult] = useState<BillingExtractionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [samplePatients, setSamplePatients] = useState<SamplePatientSummary[]>([]);
  const [selectedSamplePatientId, setSelectedSamplePatientId] = useState("");
  const [samplePatientsError, setSamplePatientsError] = useState<string | null>(null);
  const [samplePatientLoading, setSamplePatientLoading] = useState(false);

  const [roster, setRoster] = useState<Patient[]>([]);
  const [rosterError, setRosterError] = useState<string | null>(null);

  const [selectedRosterId, setSelectedRosterId] = useState<number | "">("");
  const [serviceDate, setServiceDate] = useState("");
  const [selection, setSelection] = useState<Set<number>>(new Set());

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createForm, setCreateForm] = useState(BLANK_CREATE_FORM);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const step: 1 | 2 | 3 = !source ? 1 : !result ? 2 : 3;

  useEffect(() => {
    listSamplePatients()
      .then(setSamplePatients)
      .catch((err) => setSamplePatientsError(describeError(err)));
  }, []);

  function loadRoster() {
    listPatients()
      .then(setRoster)
      .catch((err) => setRosterError(describeError(err)));
  }

  useEffect(loadRoster, []);

  // Editing the transcript, changing the sample patient, or changing the source after
  // reaching step 3 must clear everything derived from the previous extraction — otherwise
  // the physician could save codes that no longer match what's on screen.
  function clearResult() {
    setResult(null);
    setSelection(new Set());
    setSelectedRosterId("");
    setServiceDate("");
    setShowCreateForm(false);
    setSaved(false);
    setSaveError(null);
  }

  function chooseSource() {
    setSource("simule");
  }

  function changeSource() {
    setSource(null);
    clearResult();
  }

  async function handleSelectSamplePatient(id: string) {
    setSelectedSamplePatientId(id);
    clearResult();
    if (!id) {
      setTranscript("");
      return;
    }
    setSamplePatientLoading(true);
    setError(null);
    try {
      const patient = await getSamplePatient(id);
      setTranscript(patient.transcript);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSamplePatientLoading(false);
    }
  }

  function handleTranscriptChange(value: string) {
    setTranscript(value);
    if (result) clearResult();
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    setLoading(true);
    setError(null);
    clearResult();
    try {
      const response = await extractBillingCodes(transcript, source);
      setResult(response);
      setSelectedRosterId(response.patient_suggestion?.matched_patient_id ?? "");
      setServiceDate(response.encounter_date ?? "");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  function toggleCode(index: number) {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  function startCreatePatient() {
    const extracted = result?.patient_suggestion?.extracted;
    setCreateForm({
      full_name: extracted?.suggested_full_name ?? "",
      ramq_number: extracted?.suggested_ramq_number ?? "",
      date_of_birth: extracted?.suggested_date_of_birth ?? "",
      gender: extracted?.suggested_gender ?? null,
    });
    setCreateError(null);
    setShowCreateForm(true);
  }

  async function handleCreatePatient(event: FormEvent) {
    event.preventDefault();
    setCreateError(null);
    if (!createForm.full_name.trim() || !createForm.date_of_birth) {
      setCreateError("Le nom et la date de naissance sont obligatoires.");
      return;
    }
    setCreating(true);
    try {
      const payload: PatientInput = {
        full_name: createForm.full_name.trim(),
        ramq_number: createForm.ramq_number.trim() || null,
        date_of_birth: createForm.date_of_birth,
        gender: createForm.gender,
        is_registered_with_physician: false,
        is_vulnerable: false,
      };
      // Does not re-run /extract — that would burn two more LLM calls and the 10/minute limit.
      const created = await createPatient(payload);
      loadRoster();
      setSelectedRosterId(created.id);
      setShowCreateForm(false);
    } catch (err) {
      setCreateError(describeError(err));
    } finally {
      setCreating(false);
    }
  }

  const selectedCodes = useMemo(() => {
    if (!result) return [];
    return [...selection]
      .sort((a, b) => a - b)
      .map((i) => result.billing.result.codes[i]);
  }, [result, selection]);

  const totalAmount = selectedCodes.reduce((sum, c) => sum + (c.fee.amount ?? 0), 0);
  const codesMissingFee = selectedCodes.filter((c) => c.fee.amount == null).length;

  async function handleSave(confirmDuplicate: boolean) {
    if (!result || !selectedRosterId || !serviceDate || selection.size === 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      const payload: BillingRecordInput = {
        patient_id: selectedRosterId,
        service_date: serviceDate,
        billing_extraction_record_id: result.billing_extraction_record_id,
        summary_extraction_record_id: result.summary_extraction_record_id,
        selected_codes: [...new Set(selectedCodes.map((c) => c.code))],
        source_system: source,
      };
      await createBillingRecord(payload, confirmDuplicate);
      setSaved(true);
    } catch (err) {
      // Only offer the confirm-and-retry dance on the first attempt: re-submitting the
      // exact same extraction (as opposed to the same patient/date via a different one) is
      // never overridable server-side, so retrying with confirmDuplicate=true would 409
      // again forever. Surfacing it as a plain error here breaks that loop.
      if (err instanceof DuplicateBillingRecordError && !confirmDuplicate) {
        if (window.confirm(`${err.message} Enregistrer quand même ?`)) {
          await handleSave(true);
          return;
        }
        return;
      }
      setSaveError(describeError(err));
    } finally {
      setSaving(false);
    }
  }

  const suggestion = result?.patient_suggestion ?? null;
  const extracted = suggestion?.extracted ?? null;
  const matchedId = suggestion?.matched_patient_id ?? null;
  // The match is purely NAM-based, independent of name spelling — show the roster's own
  // name rather than the transcript's (which may be a nickname, typo, or absent entirely).
  const matchedPatientName = matchedId != null ? roster.find((p) => p.id === matchedId)?.full_name : null;

  return (
    <section className="page-panel">
      <h1>Extraction de codes</h1>
      <p className="lede">
        Collez une transcription ci-dessous, ou chargez un patient simulé. Les codes sont des
        suggestions seulement — vérifiez chacun par rapport à la transcription avant de
        soumettre à la RAMQ.
      </p>

      <ol className="stepper">
        <li className={`stepper-item${step === 1 ? " active" : step > 1 ? " done" : ""}`}>
          1. Source d&rsquo;importation
        </li>
        <li className={`stepper-item${step === 2 ? " active" : step > 2 ? " done" : ""}`}>
          2. Note de consultation
        </li>
        <li className={`stepper-item${step === 3 ? " active" : ""}`}>3. Révision et facturation</li>
      </ol>

      {step === 1 ? (
        <ol className="source-list">
          <li>
            <button type="button" className="source-card" onClick={chooseSource}>
              Patient simulé
            </button>
          </li>
          <li>
            <button type="button" className="source-card" disabled>
              Epic
              <span className="source-card-badge">Bientôt disponible</span>
            </button>
          </li>
          <li>
            <button type="button" className="source-card" disabled>
              Plume AI
              <span className="source-card-badge">Bientôt disponible</span>
            </button>
          </li>
        </ol>
      ) : (
        <>
          <p className="status-inline">
            Source : Patient simulé{" "}
            <button type="button" className="link-button" onClick={changeSource}>
              Changer
            </button>
          </p>

          <div className="field-row">
            <label htmlFor="patient-select">Patient simulé :</label>
            <Select
              id="patient-select"
              value={selectedSamplePatientId}
              onChange={(e) => handleSelectSamplePatient(e.target.value)}
              disabled={samplePatientLoading || samplePatients.length === 0}
            >
              <option value="">
                {samplePatients.length === 0 ? "Aucun patient simulé disponible" : "Sélectionnez un patient..."}
              </option>
              {samplePatients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </Select>
            {samplePatientLoading && <span className="status-inline">Chargement...</span>}
            {samplePatientsError && (
              <Banner tone="error">Impossible de charger la liste des patients : {samplePatientsError}</Banner>
            )}
          </div>

          <form onSubmit={handleSubmit}>
            <TextArea
              value={transcript}
              onChange={(e) => handleTranscriptChange(e.target.value)}
              rows={12}
              placeholder="Collez la transcription de la consultation ici, ou sélectionnez un patient simulé ci-dessus..."
            />
            <Button type="submit" disabled={loading || !transcript.trim()}>
              {loading ? "Extraction en cours..." : "Extraire les codes de facturation"}
            </Button>
          </form>
        </>
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {step === 3 && result && (
        <section className="results">
          <h2>Révision et facturation ({result.billing.model})</h2>
          {result.billing.result.notes && <Banner tone="warning">⚠ {result.billing.result.notes}</Banner>}

          <div className="patient-match">
            {matchedId != null ? (
              <Banner tone="success">
                Patient identifié par son NAM : {matchedPatientName ?? extracted?.suggested_full_name}
              </Banner>
            ) : extracted?.suggested_ramq_number ? (
              <Banner tone="warning">
                Aucun patient de votre liste ne correspond au NAM &laquo; {extracted.suggested_ramq_number} &raquo;
                {extracted.suggested_full_name ? ` (${extracted.suggested_full_name})` : ""}
              </Banner>
            ) : (
              <Banner tone="warning">
                Aucun NAM n&rsquo;a été trouvé dans la note — sélectionnez le patient
              </Banner>
            )}

            <label htmlFor="roster-select">Patient</label>
            <Select
              id="roster-select"
              value={selectedRosterId}
              onChange={(e) => setSelectedRosterId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Sélectionnez un patient...</option>
              {roster.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name}
                </option>
              ))}
            </Select>
            {rosterError && <Banner tone="error">{rosterError}</Banner>}

            {matchedId == null && (
              <Button type="button" variant="secondary" onClick={startCreatePatient}>
                Créer ce patient
              </Button>
            )}

            {showCreateForm && (
              <Card>
                <h3>Nouveau patient</h3>
                <form onSubmit={handleCreatePatient} className="login-form">
                  <label htmlFor="create-full-name">Nom complet</label>
                  <TextField
                    id="create-full-name"
                    value={createForm.full_name}
                    onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
                  />

                  <label htmlFor="create-ramq">Numéro RAMQ (NAM)</label>
                  <TextField
                    id="create-ramq"
                    value={createForm.ramq_number}
                    onChange={(e) => setCreateForm({ ...createForm, ramq_number: e.target.value })}
                  />

                  <label htmlFor="create-dob">Date de naissance</label>
                  <TextField
                    id="create-dob"
                    type="date"
                    value={createForm.date_of_birth}
                    onChange={(e) => setCreateForm({ ...createForm, date_of_birth: e.target.value })}
                  />
                  {extracted?.date_of_birth_is_estimated && (
                    <span className="status-inline">estimée d&rsquo;après l&rsquo;âge — à confirmer</span>
                  )}

                  <label htmlFor="create-gender">Genre</label>
                  <Select
                    id="create-gender"
                    value={createForm.gender ?? ""}
                    onChange={(e) => setCreateForm({ ...createForm, gender: (e.target.value || null) as Gender | null })}
                  >
                    <option value="">—</option>
                    {GENDERS.map((g) => (
                      <option key={g} value={g}>
                        {g}
                      </option>
                    ))}
                  </Select>

                  {createError && <Banner tone="error">{createError}</Banner>}

                  <div className="table-actions">
                    <Button type="submit" disabled={creating}>
                      {creating ? "Création..." : "Créer le patient"}
                    </Button>
                    <Button type="button" variant="secondary" onClick={() => setShowCreateForm(false)} disabled={creating}>
                      Annuler
                    </Button>
                  </div>
                </form>
              </Card>
            )}
          </div>

          <div className="field-row">
            <label htmlFor="service-date">Date de la consultation</label>
            <TextField
              id="service-date"
              type="date"
              value={serviceDate}
              onChange={(e) => setServiceDate(e.target.value)}
            />
            {!result.encounter_date && result.encounter_date_raw && (
              <span className="status-inline">
                Date non reconnue : &laquo; {result.encounter_date_raw} &raquo;
              </span>
            )}
          </div>

          {result.billing.result.codes.length === 0 ? (
            <p>Aucun code candidat n&rsquo;est clairement appuyé par cette transcription.</p>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Facturer</th>
                  <th>Code</th>
                  <th>Description</th>
                  <th>Confiance</th>
                  <th>Tarif</th>
                  <th>Citation à l&rsquo;appui</th>
                </tr>
              </thead>
              <tbody>
                {result.billing.result.codes.map((c, i) => (
                  <tr key={i}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selection.has(i)}
                        onChange={() => toggleCode(i)}
                        aria-label={`Facturer le code ${c.code}`}
                      />
                    </td>
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

          <p>
            Total indicatif : {totalAmount.toFixed(2)} $
            {codesMissingFee > 0 && ` (${codesMissingFee} code${codesMissingFee > 1 ? "s" : ""} sans tarif)`}
          </p>

          <Button
            type="button"
            onClick={() => handleSave(false)}
            disabled={saving || saved || !selectedRosterId || !serviceDate || selection.size === 0}
          >
            {saving ? "Enregistrement..." : "Enregistrer la facturation"}
          </Button>

          {saveError && <Banner tone="error">{saveError}</Banner>}
          {saved && (
            <Banner tone="success">
              Facturation enregistrée. <Link to="/app/facturation">Voir la facturation</Link>
            </Banner>
          )}
        </section>
      )}
    </section>
  );
}
