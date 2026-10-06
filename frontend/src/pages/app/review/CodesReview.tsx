import { cn } from "@/lib/utils";
import { Checkbox, Select } from "../../../components";
import type {
  ConfidenceLevel,
  ExtractedCode,
  ExtractedFee,
} from "../../../api";
import {
  buildFeeOptions,
  defaultLieu,
  feeDetails,
  formatAmount,
  optionValue,
} from "./feeOptions";

const CONFIDENCE_CLASSES: Record<ConfidenceLevel, string> = {
  high: "bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]",
  medium:
    "bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
  low: "bg-[color:var(--color-danger-bg)] text-destructive",
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

// What a lone fee shows beside its amount; a fee with several lieux gets a selector instead.
function singleFeeDetails(fee: ExtractedFee): string {
  return [fee.lieux[0], feeDetails(fee)].filter(Boolean).join(" — ");
}

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
    const options = buildFeeOptions(c.fees);
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
          <div className="flex items-start gap-3">
            <label
              htmlFor={`code-${i}`}
              className={cn("flex min-w-0 flex-1 items-baseline gap-[0.6rem]", !disabled && "cursor-pointer")}
            >
              <span
                className={cn(
                  "-rotate-[1.5deg] rounded-lg border-2 border-foreground px-[0.55rem] py-[0.2rem] font-mono text-base font-[650] text-foreground",
                  checked && "border-primary text-primary",
                )}
              >
                {c.code}
              </span>
              <span className="min-w-0 flex-1 font-heading font-semibold">
                {c.description}
              </span>
            </label>
            <span
              className={cn(
                "inline-flex shrink-0 items-center rounded-full px-[0.55rem] py-[0.15rem] text-[0.82rem] font-[650] whitespace-nowrap",
                CONFIDENCE_CLASSES[bucket],
              )}
            >
              {CONFIDENCE_LABELS[bucket]}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-[0.6rem]">
            {options.length > 1 ? (
              <>
                <Select
                  containerClassName="w-fit max-w-full"
                  value={optionValue(feeIndex, lieu)}
                  disabled={disabled}
                  onChange={(event) => {
                    const picked = options.find(
                      (o) =>
                        optionValue(o.feeIndex, o.lieu) === event.target.value,
                    );
                    if (picked) onFeeSelected(i, picked.feeIndex, picked.lieu);
                  }}
                  aria-label={`Tarif pour le code ${c.code}`}
                >
                  {options.map((o) => (
                    <option
                      key={optionValue(o.feeIndex, o.lieu)}
                      value={optionValue(o.feeIndex, o.lieu)}
                    >
                      {o.label}
                    </option>
                  ))}
                </Select>
                <span className="font-heading font-bold whitespace-nowrap">
                  {formatAmount(c.fees[feeIndex])}
                </span>
              </>
            ) : c.fees.length === 1 ? (
              <>
                <span className="font-heading font-bold whitespace-nowrap">
                  {formatAmount(c.fees[0])}
                </span>
                {singleFeeDetails(c.fees[0]) && (
                  <span className="min-w-0 text-[0.85rem] text-muted-foreground">
                    {singleFeeDetails(c.fees[0])}
                  </span>
                )}
              </>
            ) : (
              <span className="font-heading font-bold">—</span>
            )}
          </div>

          {c.explanation && (
            <p className="m-0 text-[0.92rem] text-muted-foreground">{c.explanation}</p>
          )}

          {c.needs_confirmation.length > 0 && (
            <ul className="m-0 flex flex-col gap-1 pl-0 text-[0.85rem] text-[color:var(--color-warning-text)]">
              {c.needs_confirmation.map((note, noteIndex) => (
                <li key={noteIndex} className="list-none">
                  ⚠ {note}
                </li>
              ))}
            </ul>
          )}
        </div>
      </li>
    );
  };

  // Low-confidence codes stay out of sight unless the physician asks, or already ticked one.
  const likely = sorted.filter(({ c }) => c.confidence !== "low");
  const unlikely = sorted.filter(({ c }) => c.confidence === "low");

  return (
    <div className="flex flex-col gap-3">
      {likely.length > 0 && (
        <ul className="m-0 flex flex-col gap-3 p-0">
          {likely.map(renderCode)}
        </ul>
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
