import { ArrowRight } from "lucide-react";
import { Banner, Button } from "../../../components";
import { formatMoney } from "../../../utils/money";

interface SaveSummaryProps {
  totalAmount: number;
  codesMissingFee: number;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
  canSave: boolean;
  // Saving replaces the encounter's existing claim.
  editing: boolean;
  // Shown, not editable: no save button at all.
  readOnly: boolean;
  onSave: () => void;
  // There's a next encounter to go to: save then go there, or just go when there's nothing to save.
  onSaveAndNext?: () => void;
  onNext?: () => void;
}

// The review's total and actions, kept in view at the bottom of the screen while the
// physician scrolls through the codes.
export function SaveSummary({
  totalAmount,
  codesMissingFee,
  saving,
  saveError,
  saved,
  canSave,
  editing,
  readOnly,
  onSave,
  onSaveAndNext,
  onNext,
}: SaveSummaryProps) {
  const savable = !readOnly && canSave && !saved;
  return (
    <div className="sticky bottom-0 z-10 -mx-4 -mb-4 flex flex-col gap-3 rounded-b-xl border-t border-border bg-card px-4 py-3 shadow-[0_-6px_12px_-10px_rgb(0_0_0/0.25)]">
      {saveError && <Banner tone="error">{saveError}</Banner>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-[0.6rem]">
          <span className="text-sm text-muted-foreground">Total indicatif</span>
          <span className="font-heading text-[1.6rem] font-bold tabular-nums">{formatMoney(totalAmount)}</span>
          {codesMissingFee > 0 && (
            <span className="text-sm text-muted-foreground">
              ({codesMissingFee} code{codesMissingFee > 1 ? "s" : ""} sans montant en $)
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {savable && (
            <span className="hidden text-xs text-muted-foreground xl:inline" aria-hidden>
              <kbd className="rounded border border-border bg-muted px-1 py-px font-sans">Ctrl</kbd> +{" "}
              <kbd className="rounded border border-border bg-muted px-1 py-px font-sans">Entrée</kbd>
            </span>
          )}
          {!readOnly && (
            <Button
              type="button"
              variant={onSaveAndNext && savable ? "secondary" : "primary"}
              onClick={onSave}
              disabled={saving || !savable}
            >
              {saving ? "Enregistrement..." : editing ? "Enregistrer les modifications" : "Enregistrer la facturation"}
            </Button>
          )}
          {onSaveAndNext && savable ? (
            <Button type="button" onClick={onSaveAndNext} disabled={saving}>
              Enregistrer et suivante
              <ArrowRight aria-hidden />
            </Button>
          ) : (
            onNext && (
              <Button type="button" variant="secondary" onClick={onNext} disabled={saving}>
                Suivante
                <ArrowRight aria-hidden />
              </Button>
            )
          )}
        </div>
      </div>
    </div>
  );
}
