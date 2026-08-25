import { Banner, Button, Card, TextField } from "../../../components";
import type { BillingExtractionResponse, Patient } from "../../../api";
import { PatientMatchSection } from "./PatientMatchSection";
import { CodesReview } from "./CodesReview";
import { SaveSummary } from "./SaveSummary";
import type { useCreatePatientForm } from "./useCreatePatientForm";

interface ReviewStepProps {
  result: BillingExtractionResponse;
  onBack: () => void;
  roster: Patient[];
  rosterError: string | null;
  selectedRosterId: number | "";
  onSelectRoster: (id: number | "") => void;
  onStartCreatePatient: () => void;
  createPatientForm: ReturnType<typeof useCreatePatientForm>;
  serviceDate: string;
  onServiceDateChange: (value: string) => void;
  selection: Set<number>;
  onToggleCode: (index: number) => void;
  totalAmount: number;
  codesMissingFee: number;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
  canSave: boolean;
  onSave: () => void;
}

export function ReviewStep({
  result,
  onBack,
  roster,
  rosterError,
  selectedRosterId,
  onSelectRoster,
  onStartCreatePatient,
  createPatientForm,
  serviceDate,
  onServiceDateChange,
  selection,
  onToggleCode,
  totalAmount,
  codesMissingFee,
  saving,
  saveError,
  saved,
  canSave,
  onSave,
}: ReviewStepProps) {
  const suggestion = result.patient_suggestion;
  const extracted = suggestion?.extracted ?? null;
  const matchedId = suggestion?.matched_patient_id ?? null;
  // The match is purely NAM-based, independent of name spelling — show the roster's own
  // name rather than the transcript's (which may be a nickname, typo, or absent entirely).
  const matchedPatientName = matchedId != null ? roster.find((p) => p.id === matchedId)?.full_name : null;

  return (
    <section className="results">
      <p className="status-inline">
        <Button type="button" variant="link" onClick={onBack}>
          ← Modifier la transcription
        </Button>
      </p>
      <Card className="results-card">
        <h2>Révision</h2>
        {result.billing.result.notes && <Banner tone="warning">⚠ {result.billing.result.notes}</Banner>}

        <PatientMatchSection
          matchedId={matchedId}
          matchedPatientName={matchedPatientName}
          extracted={extracted}
          roster={roster}
          rosterError={rosterError}
          selectedRosterId={selectedRosterId}
          onSelectRoster={onSelectRoster}
          onStartCreatePatient={onStartCreatePatient}
          createPatientForm={createPatientForm}
        />

        <div className="field-row">
          <label htmlFor="service-date">Date de la consultation</label>
          <TextField
            id="service-date"
            type="date"
            value={serviceDate}
            onChange={(e) => onServiceDateChange(e.target.value)}
          />
          {!result.encounter_date && result.encounter_date_raw && (
            <span className="status-inline">Date non reconnue : &laquo; {result.encounter_date_raw} &raquo;</span>
          )}
        </div>

        <CodesReview codes={result.billing.result.codes} selection={selection} onToggle={onToggleCode} />

        <SaveSummary
          totalAmount={totalAmount}
          codesMissingFee={codesMissingFee}
          saving={saving}
          saveError={saveError}
          saved={saved}
          canSave={canSave}
          onSave={onSave}
        />
      </Card>
    </section>
  );
}
