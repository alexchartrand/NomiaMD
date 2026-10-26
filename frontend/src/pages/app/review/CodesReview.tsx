import { Checkbox } from "../../../components";
import type { ConfidenceLevel, ExtractedCode } from "../../../api";
import { CODE_LIST_CLASS, CodeRow, type CodeRowTone } from "./CodeRow";
import { defaultLieu } from "./feeOptions";
import { FeeAmount, FeePicker } from "./FeePicker";

const CONFIDENCE_TONES: Record<ConfidenceLevel, CodeRowTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  high: "Confiance élevée",
  medium: "Confiance moyenne",
  low: "Confiance faible",
};

const CONFIDENCE_ORDER: Record<ConfidenceLevel, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

interface CodesReviewProps {
  codes: ExtractedCode[];
  selection: Set<number>;
  onToggle: (index: number) => void;
  feeSelection: Map<number, number>;
  lieuSelection: Map<number, string>;
  onFeeSelected: (index: number, feeIndex: number, lieu: string | null) => void;
  // The physician is looking at a code (hover or focus): its supporting quote gets marked in the note.
  onCodeFocused?: (index: number) => void;
  // Shown, not editable.
  disabled?: boolean;
}

export function CodesReview({
  codes,
  selection,
  onToggle,
  feeSelection,
  lieuSelection,
  onFeeSelected,
  onCodeFocused,
  disabled = false,
}: CodesReviewProps) {
  if (codes.length === 0) {
    return (
      <p>
        Aucun code candidat n&rsquo;est clairement appuyé par cette
        transcription.
      </p>
    );
  }

  const sorted = codes
    .map((c, i) => ({ c, i }))
    .sort(
      (a, b) =>
        CONFIDENCE_ORDER[a.c.confidence] - CONFIDENCE_ORDER[b.c.confidence],
    );

  const renderCode = ({ c, i }: { c: ExtractedCode; i: number }) => {
    const checked = selection.has(i);
    const feeIndex = feeSelection.get(i) ?? 0;
    const lieu = c.fees[feeIndex]
      ? (lieuSelection.get(i) ?? defaultLieu(c.fees[feeIndex]))
      : null;
    return (
      <CodeRow
        key={i}
        onMouseEnter={() => onCodeFocused?.(i)}
        onFocus={() => onCodeFocused?.(i)}
        code={c.code}
        description={c.description}
        controlId={`code-${i}`}
        control={
          <Checkbox
            id={`code-${i}`}
            checked={checked}
            disabled={disabled}
            onCheckedChange={() => onToggle(i)}
            aria-label={`Facturer le code ${c.code}`}
          />
        }
        tone={CONFIDENCE_TONES[c.confidence]}
        toneLabel={CONFIDENCE_LABELS[c.confidence]}
        selected={checked}
        amount={<FeeAmount fees={c.fees} feeIndex={feeIndex} />}
        details={
          <FeePicker
            code={c.code}
            fees={c.fees}
            feeIndex={feeIndex}
            lieu={lieu}
            onSelect={(chosenFee, chosenLieu) => onFeeSelected(i, chosenFee, chosenLieu)}
            disabled={disabled}
          />
        }
        warnings={c.needs_confirmation}
        explanation={c.explanation || undefined}
      />
    );
  };

  // The codes the model is sure of first; then the other possible ones, the low-confidence
  // ones out of sight unless the physician asks, or already ticked one.
  const retained = sorted.filter(({ c }) => c.retained);
  const possible = sorted.filter(({ c }) => !c.retained && c.confidence !== "low");
  const unlikely = sorted.filter(({ c }) => !c.retained && c.confidence === "low");

  return (
    <div className="flex flex-col gap-3">
      {retained.length > 0 && (
        <section aria-label="Codes retenus" className="flex flex-col gap-1.5">
          <h3 className="m-0 font-heading text-sm font-semibold text-muted-foreground">Codes retenus</h3>
          <ul className={CODE_LIST_CLASS}>{retained.map(renderCode)}</ul>
        </section>
      )}
      {possible.length > 0 && (
        <section aria-label="Autres possibilités" className="flex flex-col gap-1.5">
          <h3 className="m-0 font-heading text-sm font-semibold text-muted-foreground">Autres possibilités</h3>
          <ul className={CODE_LIST_CLASS}>{possible.map(renderCode)}</ul>
        </section>
      )}
      {unlikely.length > 0 && (
        <details
          open={unlikely.some(({ i }) => selection.has(i))}
          className="rounded-lg border border-border px-3 py-2"
        >
          <summary className="cursor-pointer font-heading text-sm font-semibold">
            Autres codes ({unlikely.length})
          </summary>
          <ul className={`${CODE_LIST_CLASS} mt-2`}>
            {unlikely.map(renderCode)}
          </ul>
        </details>
      )}
    </div>
  );
}
