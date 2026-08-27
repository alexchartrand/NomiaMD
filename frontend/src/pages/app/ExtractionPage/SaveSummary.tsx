import { Link } from "react-router-dom";
import { Banner, Button } from "../../../components";

interface SaveSummaryProps {
  totalAmount: number;
  codesMissingFee: number;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
  canSave: boolean;
  onSave: () => void;
}

export function SaveSummary({ totalAmount, codesMissingFee, saving, saveError, saved, canSave, onSave }: SaveSummaryProps) {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border pt-[0.85rem]">
        <div className="flex items-baseline gap-[0.6rem]">
          <span className="text-sm text-muted-foreground">Total indicatif</span>
          <span className="font-heading text-[1.6rem] font-bold">{totalAmount.toFixed(2)} $</span>
          {codesMissingFee > 0 && (
            <span className="text-sm text-muted-foreground">
              ({codesMissingFee} code{codesMissingFee > 1 ? "s" : ""} sans tarif)
            </span>
          )}
        </div>

        <Button type="button" onClick={onSave} disabled={saving || saved || !canSave}>
          {saving ? "Enregistrement..." : "Enregistrer la facturation"}
        </Button>
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
