import { useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, TextField } from "../../../components";
import type { BillingExtractionResponse } from "../../../api";
import { AddedCodes } from "./AddedCodes";
import { CodesReview } from "./CodesReview";
import { ConsultationSummary } from "./ConsultationSummary";
import { FrequentCodes } from "./FrequentCodes";
import { manualEntries } from "./manualCodes";
import { NotePanel } from "./NotePanel";
import { SaveSummary } from "./SaveSummary";
import { locateQuote } from "./quoteLocator";
import type { CodeReview } from "./useCodeReview";

interface ReviewStepProps {
  result: BillingExtractionResponse;
  // null once the note was removed past retention (see NotePanel).
  noteText: string | null;
  noteScrubbedAt?: string | null;
  // The encounter's patient: codes added from the search are the ones they may be billed.
  patientId: number;
  review: CodeReview;
  // Set when there's a next encounter in the list this one was opened from.
  onSaveAndNext?: () => void;
  onNext?: () => void;
}

// The proposed codes to tick, under the summary of the note they were read from; the note
// itself, collapsed, below them.
export function ReviewStep({
  result,
  noteText,
  noteScrubbedAt = null,
  patientId,
  review,
  onSaveAndNext,
  onNext,
}: ReviewStepProps) {
  const { state } = review;
  const codes = result.billing.codes;
  const quotes = useMemo(
    () => codes.map((c) => (noteText === null ? null : locateQuote(noteText, c.supporting_quote))),
    [codes, noteText],
  );
  // The code whose supporting quote is marked in the note: the last one hovered or focused.
  const [focused, setFocused] = useState<number | null>(null);
  const added = manualEntries(state.manual);
  const ticked = codes.filter((_, i) => state.selection.has(i)).map((c) => c.code);

  return (
    <div className="flex flex-col gap-4">
      <ConsultationSummary summary={result.summary} />

      <Card className="overflow-visible">
        <CardHeader className="flex flex-wrap items-start justify-between gap-3">
          <CardTitle className="font-heading text-lg font-bold">Codes proposés</CardTitle>
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
          <CodesReview
            codes={codes}
            selection={state.selection}
            onToggle={review.toggleCode}
            feeSelection={state.feeSelection}
            lieuSelection={state.lieuSelection}
            onFeeSelected={review.selectFee}
            onCodeFocused={setFocused}
            disabled={review.readOnly}
          />

          {!review.readOnly && (
            // A frequent code the extraction proposed, unticked, gets ticked rather than added twice.
            <FrequentCodes
              patientId={patientId}
              serviceDate={state.serviceDate || null}
              onAdd={review.addCode}
              excludeNumbers={[...ticked, ...added.map((e) => e.hit.number)]}
            />
          )}

          <AddedCodes
            entries={added}
            onAdd={review.addCode}
            onRemove={review.removeCode}
            onFeeSelected={review.selectAddedFee}
            patientId={patientId}
            serviceDate={state.serviceDate || null}
            excludeNumbers={ticked}
            searchLabel="Ajouter un code non proposé"
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

      <NotePanel text={noteText} scrubbedAt={noteScrubbedAt} highlight={focused !== null ? quotes[focused] : null} />
    </div>
  );
}
