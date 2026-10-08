import { cn } from "@/lib/utils";
import { Badge, Checkbox, type BadgeTone } from "../../../components";
import type { ConfidenceLevel, ExtractedCode } from "../../../api";
import { defaultLieu } from "./feeOptions";
import { FeePicker } from "./FeePicker";
import { NeedsConfirmation } from "./NeedsConfirmation";

const CONFIDENCE_TONES: Record<ConfidenceLevel, BadgeTone> = {
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
    const bucket = c.confidence;
    const feeIndex = feeSelection.get(i) ?? 0;
    const lieu = c.fees[feeIndex]
      ? (lieuSelection.get(i) ?? defaultLieu(c.fees[feeIndex]))
      : null;
    return (
      <li
        key={i}
        onMouseEnter={() => onCodeFocused?.(i)}
        onFocus={() => onCodeFocused?.(i)}
        className={cn(
          "flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-[0.9rem] transition-colors",
          checked && "border-primary bg-[color:var(--color-primary-tint)]",
        )}
      >
        <Checkbox
          id={`code-${i}`}
          className="mt-[0.3rem]"
          checked={checked}
          disabled={disabled}
          onCheckedChange={() => onToggle(i)}
          aria-label={`Facturer le code ${c.code}`}
        />

        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <label
            htmlFor={`code-${i}`}
            className={cn("flex min-w-0 flex-col gap-1.5", !disabled && "cursor-pointer")}
          >
            <span className="flex items-center justify-between gap-3">
              <span
                className={cn(
                  "-rotate-[1.5deg] rounded-lg border-2 border-foreground px-[0.55rem] py-[0.2rem] font-mono text-base font-[650] text-foreground",
                  checked && "border-primary text-primary",
                )}
              >
                {c.code}
              </span>
              <Badge tone={CONFIDENCE_TONES[bucket]}>{CONFIDENCE_LABELS[bucket]}</Badge>
            </span>
            <span className="font-heading text-[0.95rem] leading-snug font-semibold">{c.description}</span>
          </label>

          <FeePicker
            code={c.code}
            fees={c.fees}
            feeIndex={feeIndex}
            lieu={lieu}
            onSelect={(chosenFee, chosenLieu) => onFeeSelected(i, chosenFee, chosenLieu)}
            disabled={disabled}
          />

          {c.explanation && (
            <p className="m-0 text-[0.92rem] text-muted-foreground">{c.explanation}</p>
          )}

          <NeedsConfirmation notes={c.needs_confirmation} />
        </div>
      </li>
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
        <section aria-label="Codes retenus" className="flex flex-col gap-2">
          <h3 className="m-0 font-heading text-sm font-semibold text-muted-foreground">Codes retenus</h3>
          <ul className="m-0 flex flex-col gap-3 p-0">{retained.map(renderCode)}</ul>
        </section>
      )}
      {possible.length > 0 && (
        <section aria-label="Autres possibilités" className="flex flex-col gap-2">
          <h3 className="m-0 font-heading text-sm font-semibold text-muted-foreground">Autres possibilités</h3>
          <ul className="m-0 flex flex-col gap-3 p-0">{possible.map(renderCode)}</ul>
        </section>
      )}
      {unlikely.length > 0 && (
        <details
          open={unlikely.some(({ i }) => selection.has(i))}
          className="rounded-xl border border-border px-4 py-3"
        >
          <summary className="cursor-pointer font-heading font-semibold">
            Autres codes ({unlikely.length})
          </summary>
          <ul className="m-0 mt-3 flex flex-col gap-3 p-0">
            {unlikely.map(renderCode)}
          </ul>
        </details>
      )}
    </div>
  );
}
