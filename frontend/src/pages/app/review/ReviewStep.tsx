import { useMemo, useState } from "react";
import { Banner, Card, CardContent, CardHeader, CardTitle, TextField } from "../../../components";
import type { BillingExtractionResponse } from "../../../api";
import { useMediaQuery } from "../../../lib/useMediaQuery";
import { CodesReview } from "./CodesReview";
import { NotePanel } from "./NotePanel";
import { SaveSummary } from "./SaveSummary";
import { locateQuote } from "./quoteLocator";
import type { CodeReview } from "./useCodeReview";

// Wide enough, beside the sidebar, for the note and the codes side by side.
const SIDE_BY_SIDE = "(min-width: 1400px)";

interface ReviewStepProps {
  result: BillingExtractionResponse;
  noteText: string;
  review: CodeReview;
  // Set when there's a next encounter in the list this one was opened from.
  onSaveAndNext?: () => void;
  onNext?: () => void;
}

// The proposed codes to tick, beside the note they were read from.
export function ReviewStep({ result, noteText, review, onSaveAndNext, onNext }: ReviewStepProps) {
  const { state } = review;
  const docked = useMediaQuery(SIDE_BY_SIDE);
  const codes = result.billing.result.codes;
  const quotes = useMemo(() => codes.map((c) => locateQuote(noteText, c.supporting_quote)), [codes, noteText]);
  // The code whose quote is marked in the note: the last one hovered, focused or asked for.
  const [focused, setFocused] = useState<number | null>(null);
  const [reveal, setReveal] = useState(0);

  const note = (
    <NotePanel
      text={noteText}
      highlight={focused !== null ? quotes[focused] : null}
      reveal={reveal}
      docked={docked}
    />
  );

  return (
    <div className={docked ? "grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-start gap-6" : "flex flex-col gap-4"}>
      {docked && note}

      <Card className="overflow-visible">
        <CardHeader className="flex flex-wrap items-start justify-between gap-3">
          <CardTitle className="text-[1.3rem] font-bold">Codes proposés</CardTitle>
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <label htmlFor="service-date" className="text-sm text-muted-foreground">
                Date de la consultation
              </label>
              <TextField
                id="service-date"
                type="date"
                className="w-auto"
                value={state.serviceDate}
                disabled={review.readOnly}
                onChange={(e) => review.changeServiceDate(e.target.value)}
              />
            </div>
            {!result.encounter_date && result.encounter_date_raw && (
              <span className="text-sm text-muted-foreground">
                Date non reconnue : &laquo; {result.encounter_date_raw} &raquo;
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-[0.85rem]">
          {result.billing.result.notes && <Banner tone="warning">⚠ {result.billing.result.notes}</Banner>}

          <CodesReview
            codes={codes}
            selection={state.selection}
            onToggle={review.toggleCode}
            feeSelection={state.feeSelection}
            lieuSelection={state.lieuSelection}
            onFeeSelected={review.selectFee}
            quoteInNote={quotes.map((q) => q !== null)}
            onCodeFocused={setFocused}
            onShowQuote={(i) => {
              setFocused(i);
              setReveal((n) => n + 1);
            }}
            disabled={review.readOnly}
          />

          <SaveSummary
            totalAmount={review.totalAmount}
            codesMissingFee={review.codesMissingFee}
            saving={state.saving}
            saveError={state.saveError}
            saved={state.saved}
            canSave={review.canSave}
            editing={review.editing}
            readOnly={review.readOnly}
            onSave={review.save}
            onSaveAndNext={onSaveAndNext}
            onNext={onNext}
          />
        </CardContent>
      </Card>

      {!docked && note}
    </div>
  );
}
