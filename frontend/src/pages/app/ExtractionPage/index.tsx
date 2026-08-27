import { useMemo, useReducer, useState, type FormEvent } from "react";
import { createClaim, describeError, DuplicateClaimError, extractBillingCodes } from "../../../api";
import { Banner } from "../../../components";
import { SourceStep } from "./SourceStep";
import { ReviewStep } from "./ReviewStep";
import { useSamplePatients } from "./useSamplePatients";
import { useRoster } from "./useRoster";
import { useCreatePatientForm } from "./useCreatePatientForm";
import { initialReviewState, reviewReducer } from "./reviewState";

export default function ExtractionPage() {
  const [source, setSource] = useState<"simule" | null>(null);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [review, dispatch] = useReducer(reviewReducer, initialReviewState);
  const step: 1 | 2 = !review.result ? 1 : 2;

  const { roster, error: rosterError, reload: loadRoster } = useRoster();

  // Editing the transcript or changing the sample patient after an extraction (including
  // via the review page's "back" link) must clear everything derived from it — otherwise
  // the physician could save codes that no longer match what's on screen.
  function clearResult() {
    dispatch({ type: "cleared" });
    createPatientForm.close();
  }

  const samplePatientPicker = useSamplePatients({
    onBeforeSelect: () => {
      clearResult();
      setError(null);
    },
    onTranscriptLoaded: setTranscript,
    onError: setError,
  });

  const createPatientForm = useCreatePatientForm({
    onCreated: (patient) => {
      loadRoster();
      dispatch({ type: "roster-selected", id: patient.id });
    },
  });

  function chooseSource(nextSource: "simule") {
    if (nextSource === source) return;
    setSource(nextSource);
  }

  function handleTranscriptChange(value: string) {
    setTranscript(value);
    if (review.result) clearResult();
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    setLoading(true);
    setError(null);
    clearResult();
    try {
      const response = await extractBillingCodes(transcript, source);
      dispatch({ type: "extracted", result: response });
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }

  function toggleCode(index: number) {
    dispatch({ type: "code-toggled", index });
  }

  function startCreatePatient() {
    const extracted = review.result?.patient_suggestion?.extracted;
    createPatientForm.open({
      full_name: extracted?.suggested_full_name ?? "",
      ramq_number: extracted?.suggested_ramq_number ?? "",
      date_of_birth: extracted?.suggested_date_of_birth ?? "",
      gender: extracted?.suggested_gender ?? null,
    });
  }

  const selectedCodes = useMemo(() => {
    const { result, selection } = review;
    if (!result) return [];
    return [...selection].sort((a, b) => a - b).map((i) => result.billing.result.codes[i]);
  }, [review]);

  const totalAmount = selectedCodes.reduce((sum, c) => sum + (c.fee.amount ?? 0), 0);
  const codesMissingFee = selectedCodes.filter((c) => c.fee.amount == null).length;

  async function handleSave(confirmDuplicate: boolean) {
    const { result, selectedRosterId, serviceDate, selection } = review;
    if (!result || !selectedRosterId || !serviceDate || selection.size === 0) return;
    dispatch({ type: "save-started" });
    try {
      await createClaim(
        {
          patient_id: selectedRosterId,
          service_date: serviceDate,
          billing_extraction_record_id: result.billing_extraction_record_id,
          summary_extraction_record_id: result.summary_extraction_record_id,
          selected_codes: [...new Set(selectedCodes.map((c) => c.code))],
          source_system: source,
        },
        confirmDuplicate,
      );
      dispatch({ type: "save-succeeded" });
    } catch (err) {
      // Only offer the confirm-and-retry dance on the first attempt: re-submitting the
      // exact same extraction (as opposed to the same patient/date via a different one) is
      // never overridable server-side, so retrying with confirmDuplicate=true would 409
      // again forever. Surfacing it as a plain error here breaks that loop.
      if (err instanceof DuplicateClaimError && !confirmDuplicate) {
        if (window.confirm(`${err.message} Enregistrer quand même ?`)) {
          await handleSave(true);
          return;
        }
        dispatch({ type: "save-cancelled" });
        return;
      }
      dispatch({ type: "save-failed", error: describeError(err) });
    }
  }

  return (
    <section className="page-panel">
      <h1>Réclamation</h1>

      <ol className="stepper">
        <li className={`stepper-item${step === 1 ? " active" : " done"}`}>
          <span className="stepper-marker">{step > 1 ? "✓" : 1}</span>
          <span className="stepper-label">Source</span>
        </li>
        <li className={`stepper-item${step === 2 ? " active" : ""}`}>
          <span className="stepper-marker">2</span>
          <span className="stepper-label">Révision</span>
        </li>
      </ol>

      {step === 1 && (
        <SourceStep
          source={source}
          onChooseSource={chooseSource}
          samplePatients={samplePatientPicker.samplePatients}
          selectedSamplePatientId={samplePatientPicker.selectedId}
          onSelectSamplePatient={samplePatientPicker.select}
          samplePatientLoading={samplePatientPicker.loading}
          samplePatientsError={samplePatientPicker.listError}
          transcript={transcript}
          onTranscriptChange={handleTranscriptChange}
          onSubmit={handleSubmit}
          loading={loading}
        />
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {step === 2 && review.result && (
        <ReviewStep
          result={review.result}
          onBack={clearResult}
          roster={roster}
          rosterError={rosterError}
          selectedRosterId={review.selectedRosterId}
          onSelectRoster={(id) => dispatch({ type: "roster-selected", id })}
          onStartCreatePatient={startCreatePatient}
          createPatientForm={createPatientForm}
          serviceDate={review.serviceDate}
          onServiceDateChange={(date) => dispatch({ type: "service-date-changed", date })}
          selection={review.selection}
          onToggleCode={toggleCode}
          totalAmount={totalAmount}
          codesMissingFee={codesMissingFee}
          saving={review.saving}
          saveError={review.saveError}
          saved={review.saved}
          canSave={Boolean(review.selectedRosterId) && Boolean(review.serviceDate) && review.selection.size > 0}
          onSave={() => handleSave(false)}
        />
      )}
    </section>
  );
}
