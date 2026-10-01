import { Banner, Button, Card, CardContent, CardHeader, CardTitle, TextField } from "../../../components";
import type { BillingExtractionResponse, Patient } from "../../../api";
import { PatientMatchSection } from "./PatientMatchSection";
import { CodesReview } from "./CodesReview";
import { SaveSummary } from "./SaveSummary";

interface ReviewStepProps {
  result: BillingExtractionResponse;
  patient: Patient;
  onBack: () => void;
  serviceDate: string;
  onServiceDateChange: (value: string) => void;
  selection: Set<number>;
  onToggleCode: (index: number) => void;
  feeSelection: Map<number, number>;
  onFeeSelected: (index: number, feeIndex: number) => void;
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
  patient,
  onBack,
  serviceDate,
  onServiceDateChange,
  selection,
  onToggleCode,
  feeSelection,
  onFeeSelected,
  totalAmount,
  codesMissingFee,
  saving,
  saveError,
  saved,
  canSave,
  onSave,
}: ReviewStepProps) {
  return (
    <section>
      <p className="mb-2">
        <Button type="button" variant="link" onClick={onBack}>
          ← Modifier la transcription
        </Button>
      </p>
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
              value={serviceDate}
              onChange={(e) => onServiceDateChange(e.target.value)}
            />
            {!result.encounter_date && result.encounter_date_raw && (
              <span className="text-sm text-muted-foreground">
                Date non reconnue : &laquo; {result.encounter_date_raw} &raquo;
              </span>
            )}
          </div>

          <CodesReview
            codes={result.billing.result.codes}
            selection={selection}
            onToggle={onToggleCode}
            feeSelection={feeSelection}
            onFeeSelected={onFeeSelected}
          />

          <SaveSummary
            totalAmount={totalAmount}
            codesMissingFee={codesMissingFee}
            saving={saving}
            saveError={saveError}
            saved={saved}
            canSave={canSave}
            onSave={onSave}
          />
        </CardContent>
      </Card>
    </section>
  );
}
