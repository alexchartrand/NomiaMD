import { cn } from "@/lib/utils";
import { Checkbox } from "../../../components";
import type { ConfidenceLevel, ExtractedCode } from "../../../api";

const CONFIDENCE_CLASSES: Record<ConfidenceLevel, string> = {
  high: "bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]",
  medium: "bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
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

interface CodesReviewProps {
  codes: ExtractedCode[];
  selection: Set<number>;
  onToggle: (index: number) => void;
}

export function CodesReview({ codes, selection, onToggle }: CodesReviewProps) {
  if (codes.length === 0) {
    return <p>Aucun code candidat n&rsquo;est clairement appuyé par cette transcription.</p>;
  }

  const sorted = codes
    .map((c, i) => ({ c, i }))
    .sort((a, b) => CONFIDENCE_ORDER[a.c.confidence] - CONFIDENCE_ORDER[b.c.confidence]);

  return (
    <ul className="m-0 flex flex-col gap-3 p-0">
      {sorted.map(({ c, i }) => {
        const checked = selection.has(i);
        const bucket = c.confidence;
        return (
          <li
            key={i}
            className={cn(
              "flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-[0.9rem] transition-colors",
              checked && "border-primary bg-[color:var(--color-primary-tint)]",
            )}
          >
            <Checkbox
              className="mt-[0.3rem]"
              checked={checked}
              onCheckedChange={() => onToggle(i)}
              aria-label={`Facturer le code ${c.code}`}
            />

            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-baseline gap-[0.6rem]">
                <span
                  className={cn(
                    "-rotate-[1.5deg] rounded-lg border-2 border-foreground px-[0.55rem] py-[0.2rem] font-mono text-base font-[650] text-foreground",
                    checked && "border-primary text-primary",
                  )}
                >
                  {c.code}
                </span>
                <span className="min-w-0 flex-1 font-heading font-semibold">{c.description}</span>
                <span className="font-heading font-bold whitespace-nowrap">
                  {c.fee.amount != null ? `${c.fee.amount.toFixed(2)} $` : "—"}
                </span>
              </div>

              <p className="m-0 text-[0.92rem] text-muted-foreground italic">{c.explanation}</p>

              {c.needs_confirmation.length > 0 && (
                <ul className="m-0 flex flex-col gap-1 pl-0 text-[0.85rem] text-[color:var(--color-warning-text)]">
                  {c.needs_confirmation.map((note, noteIndex) => (
                    <li key={noteIndex} className="list-none">
                      ⚠ {note}
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex justify-end">
                <span
                  className={cn(
                    "inline-flex items-center rounded-full px-[0.55rem] py-[0.15rem] text-[0.82rem] font-[650]",
                    CONFIDENCE_CLASSES[bucket],
                  )}
                >
                  {CONFIDENCE_LABELS[bucket]}
                </span>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
