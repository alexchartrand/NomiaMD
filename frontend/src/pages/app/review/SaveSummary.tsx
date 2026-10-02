import { Link } from "react-router-dom";
import { Banner, Button } from "../../../components";

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
}

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
}: SaveSummaryProps) {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-[0.85rem]">
        <div className="flex items-baseline gap-[0.6rem]">
          <span className="text-sm text-muted-foreground">Total indicatif</span>
          <span className="font-heading text-[1.6rem] font-bold">{totalAmount.toFixed(2)} $</span>
          {codesMissingFee > 0 && (
            <span className="text-sm text-muted-foreground">
              ({codesMissingFee} code{codesMissingFee > 1 ? "s" : ""} sans montant en $)
            </span>
          )}
        </div>

        {!readOnly && (
          <Button type="button" onClick={onSave} disabled={saving || saved || !canSave}>
            {saving ? "Enregistrement..." : editing ? "Enregistrer les modifications" : "Enregistrer la facturation"}
          </Button>
        )}
      </div>

      {saveError && <Banner tone="error">{saveError}</Banner>}
      {saved && (
        <Banner tone="success">
          Facturation enregistrée. <Link to="/app/facturation">Voir la facturation</Link>
        </Banner>
      )}
    </>
  );
}
