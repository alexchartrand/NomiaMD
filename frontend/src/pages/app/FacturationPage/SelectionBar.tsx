import { useState } from "react";
import { FilePlus2 } from "lucide-react";
import { createBill, describeError, StaleBillSelectionError, type Bill, type Claim } from "../../../api";
import { Banner, Button } from "../../../components";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";

interface SelectionBarProps {
  selected: Claim[];
  onClear: () => void;
  onCreated: (bill: Bill) => void;
  // A ticked claim was billed or deleted elsewhere: the list needs re-reading.
  onStale: () => void;
}

// The bill's period is the one its claims span — nothing to type, never wrong.
function periodOf(claims: Claim[]): { start_date: string; end_date: string } {
  const dates = claims.map((claim) => claim.service_date).sort();
  return { start_date: dates[0], end_date: dates[dates.length - 1] };
}

// Under the claims while some are ticked: what they add up to, and one click bills them.
export function SelectionBar({ selected, onClear, onCreated, onStale }: SelectionBarProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (selected.length === 0) {
    return error ? (
      <div className="border-t border-border px-4 py-3">
        <Banner tone="error">{error}</Banner>
      </div>
    ) : null;
  }

  const period = periodOf(selected);
  const total = selected.reduce((sum, claim) => sum + (claim.total_amount ?? 0), 0);
  const count = `${selected.length} réclamation${selected.length > 1 ? "s" : ""} sélectionnée${selected.length > 1 ? "s" : ""}`;
  const span =
    period.start_date === period.end_date
      ? `le ${formatDate(period.start_date)}`
      : `du ${formatDate(period.start_date)} au ${formatDate(period.end_date)}`;

  async function generate() {
    setError(null);
    setSubmitting(true);
    try {
      onCreated(await createBill({ ...period, claim_ids: selected.map((claim) => claim.id) }));
    } catch (err) {
      if (err instanceof StaleBillSelectionError) {
        setError(`${err.message} La liste a été mise à jour, veuillez vérifier votre sélection.`);
        onStale();
      } else {
        setError(describeError(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  // Like the review's save bar: the card's last strip, kept in view at the bottom of the
  // screen while the physician scrolls through the claims.
  return (
    <div
      role="region"
      aria-label="Sélection"
      className="sticky bottom-0 z-10 flex flex-col gap-3 border-t border-border bg-card px-4 py-3 shadow-[0_-6px_12px_-10px_rgb(0_0_0/0.25)]"
    >
      {error && <Banner tone="error">{error}</Banner>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-baseline gap-x-[0.6rem] gap-y-1">
          <span className="text-sm text-muted-foreground">{count}</span>
          <span className="font-heading text-[1.6rem] font-bold tabular-nums">{formatMoney(total)}</span>
          <span className="text-sm text-muted-foreground">{span}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={submitting}
            onClick={() => {
              setError(null);
              onClear();
            }}
          >
            Désélectionner
          </Button>
          <Button type="button" onClick={generate} disabled={submitting}>
            <FilePlus2 aria-hidden />
            {submitting ? "Génération..." : "Générer la facture"}
          </Button>
        </div>
      </div>
    </div>
  );
}
