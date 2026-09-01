import { useMemo, useReducer, useState, type FormEvent } from "react";
import { cn } from "@/lib/utils";
import {
  createClaim,
  describeError,
  DuplicateClaimError,
  extractBillingCodes,
  searchPatients,
  type Patient,
} from "../../../api";
import { Banner } from "../../../components";
import { SourceStep } from "./SourceStep";
import { ReviewStep } from "./ReviewStep";
import { useSamplePatients } from "./useSamplePatients";
import { useCreatePatientForm } from "../patients/useCreatePatientForm";
import { initialReviewState, reviewReducer } from "./reviewState";

export default function ExtractionPage() {
  const [source, setSource] = useState<"simule" | null>(null);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Chosen before extraction runs (SourceStep.tsx) and fixed for the rest of the flow —
  // not part of the review reducer below, which is scoped to a single extraction result.
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);

  const [review, dispatch] = useReducer(reviewReducer, initialReviewState);
  const step: 1 | 2 = !review.result ? 1 : 2;

  // Editing the transcript or changing the sample patient after an extraction (including
  // via the review page's "back" link) must clear everything derived from it — otherwise
  // the physician could save codes that no longer match what's on screen.
  function clearResult() {
    dispatch({ type: "cleared" });
    createPatientForm.close();
  }

  // Auto-fills the real patient picker from the sample consultation's own NAM, so the two
  // pickers (which are otherwise independent — see CLAUDE.md) default to a matching pair.
  // Best-effort: if nothing matches (e.g. the dev DB hasn't been seeded from
  // consultations/) the field is simply left empty for the physician to fill in manually.
  async function handleSampleNamLoaded(nam: string | null) {
    if (!nam) return;
    try {
      const matches = await searchPatients(nam);
      const match = matches.find((p) => p.ramq_number === nam);
      if (match) setSelectedPatient(match);
    } catch {
      // ignore — leave the patient field for the physician to fill in manually
    }
  }

  const samplePatientPicker = useSamplePatients({
    onBeforeSelect: () => {
      clearResult();
      setError(null);
      setSelectedPatient(null);
    },
    onTranscriptLoaded: setTranscript,
    onNamLoaded: handleSampleNamLoaded,
    onError: setError,
  });

  const createPatientForm = useCreatePatientForm({
    onCreated: (patient) => {
      setSelectedPatient(patient);
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
    if (!source || !selectedPatient) return;
    setLoading(true);
    setError(null);
    clearResult();
    try {
      const response = await extractBillingCodes(transcript, source, selectedPatient.id);
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

  function selectFee(index: number, feeIndex: number) {
    dispatch({ type: "fee-selected", index, feeIndex });
  }

  function startCreatePatient() {
    createPatientForm.open();
  }

  const selectedEntries = useMemo(() => {
    const { result, selection, feeSelection } = review;
    if (!result) return [];
    return [...selection].sort((a, b) => a - b).map((i) => {
      const code = result.billing.result.codes[i];
      const feeIndex = code.fees.length > 0 ? (feeSelection.get(i) ?? 0) : null;
      const fee = feeIndex != null ? code.fees[feeIndex] : null;
      return { code, feeIndex, fee };
    });
  }, [review]);

  const totalAmount = selectedEntries.reduce((sum, e) => sum + (e.fee?.amount ?? 0), 0);
  const codesMissingFee = selectedEntries.filter((e) => e.fee?.amount == null).length;

  async function handleSave(confirmDuplicate: boolean) {
    const { result, serviceDate, selection } = review;
    if (!result || !selectedPatient || !serviceDate || selection.size === 0) return;
    dispatch({ type: "save-started" });
    try {
      const selectedCodes = new Map(
        selectedEntries.map((e) => [e.code.code, { code: e.code.code, fee_index: e.feeIndex }]),
      );
      await createClaim(
        {
          patient_id: selectedPatient.id,
          service_date: serviceDate,
          billing_extraction_record_id: result.billing_extraction_record_id,
          summary_extraction_record_id: result.summary_extraction_record_id,
          selected_codes: [...selectedCodes.values()],
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
    <section className="max-w-[860px]">
      <h1 className="font-heading text-2xl font-semibold">Réclamation</h1>

      <ol className="my-6 flex items-center p-0 text-[0.88rem] text-muted-foreground">
        <li
          className={cn(
            "flex flex-1 items-center gap-[0.55rem] after:mx-[0.9rem] after:h-px after:min-w-[1.5rem] after:flex-1 after:bg-border after:content-['']",
            step > 1 && "after:bg-primary after:opacity-40",
          )}
        >
          <span
            className={cn(
              "flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-card text-[0.76rem] font-[650] text-muted-foreground",
              step === 1 && "border-primary bg-primary text-white",
              step > 1 && "border-primary bg-[color:var(--color-primary-tint)] text-primary",
            )}
          >
            {step > 1 ? "✓" : 1}
          </span>
          <span
            className={cn(
              "whitespace-nowrap max-[620px]:hidden",
              step === 1 && "font-[650] text-primary",
              step > 1 && "text-foreground",
            )}
          >
            Source
          </span>
        </li>
        <li className="flex items-center gap-[0.55rem]">
          <span
            className={cn(
              "flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-card text-[0.76rem] font-[650] text-muted-foreground",
              step === 2 && "border-primary bg-primary text-white",
            )}
          >
            2
          </span>
          <span
            className={cn("whitespace-nowrap max-[620px]:hidden", step === 2 && "font-[650] text-primary")}
          >
            Révision
          </span>
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
          selectedPatient={selectedPatient}
          onSelectPatient={setSelectedPatient}
          createPatientForm={createPatientForm}
          onStartCreatePatient={startCreatePatient}
        />
      )}

      {error && <Banner tone="error">{error}</Banner>}

      {step === 2 && review.result && selectedPatient && (
        <ReviewStep
          result={review.result}
          patient={selectedPatient}
          onBack={clearResult}
          serviceDate={review.serviceDate}
          onServiceDateChange={(date) => dispatch({ type: "service-date-changed", date })}
          selection={review.selection}
          onToggleCode={toggleCode}
          feeSelection={review.feeSelection}
          onFeeSelected={selectFee}
          totalAmount={totalAmount}
          codesMissingFee={codesMissingFee}
          saving={review.saving}
          saveError={review.saveError}
          saved={review.saved}
          canSave={Boolean(review.serviceDate) && review.selection.size > 0}
          onSave={() => handleSave(false)}
        />
      )}
    </section>
  );
}
