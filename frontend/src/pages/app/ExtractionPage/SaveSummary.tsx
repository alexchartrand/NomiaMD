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
      <div className="results-summary">
        <div className="results-total">
          <span className="results-total-label">Total indicatif</span>
          <span className="results-total-amount">{totalAmount.toFixed(2)} $</span>
          {codesMissingFee > 0 && (
            <span className="status-inline">
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
