import { Banner, Card, CardContent, CardHeader, CardTitle, TextField } from "../../../components";
import type { BillingExtractionResponse } from "../../../api";
import { PatientMatchSection, type ReviewedPatient } from "./PatientMatchSection";
import { CodesReview } from "./CodesReview";
import { SaveSummary } from "./SaveSummary";
import type { CodeReview } from "./useCodeReview";

interface ReviewStepProps {
  result: BillingExtractionResponse;
  patient: ReviewedPatient;
  review: CodeReview;
}

export function ReviewStep({ result, patient, review }: ReviewStepProps) {
  const { state } = review;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-[1.3rem] font-bold">Révision</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-[0.85rem]">
        {result.billing.result.notes && <Banner tone="warning">⚠ {result.billing.result.notes}</Banner>}

        <PatientMatchSection patient={patient} />

        <div className="flex flex-col gap-[0.35rem]">
          <label htmlFor="service-date" className="text-sm text-muted-foreground">
            Date de la consultation
          </label>
          <TextField
            id="service-date"
            type="date"
            className="w-auto"
            value={state.serviceDate}
            onChange={(e) => review.changeServiceDate(e.target.value)}
          />
          {!result.encounter_date && result.encounter_date_raw && (
            <span className="text-sm text-muted-foreground">
              Date non reconnue : &laquo; {result.encounter_date_raw} &raquo;
            </span>
          )}
        </div>

        <CodesReview
          codes={result.billing.result.codes}
          selection={state.selection}
          onToggle={review.toggleCode}
          feeSelection={state.feeSelection}
          onFeeSelected={review.selectFee}
        />

        <SaveSummary
          totalAmount={review.totalAmount}
          codesMissingFee={review.codesMissingFee}
          saving={state.saving}
          saveError={state.saveError}
          saved={state.saved}
          canSave={review.canSave}
          onSave={review.save}
        />
      </CardContent>
    </Card>
  );
}
