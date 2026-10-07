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

  if (selected.length === 0) return error ? <Banner tone="error" className="mt-3">{error}</Banner> : null;

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

  return (
    <div
      role="region"
      aria-label="Sélection"
      className="sticky bottom-4 z-10 mt-3 flex flex-col gap-3 rounded-xl border border-primary/25 bg-[color:var(--color-primary-tint)] px-4 py-3 shadow-[0_6px_16px_-8px_rgb(0_0_0/0.3)]"
    >
      {error && <Banner tone="error">{error}</Banner>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-sm">
          <span className="font-semibold">{count}</span>
          <span className="text-muted-foreground">
            {" "}
            · <span className="tabular-nums">{formatMoney(total)}</span> · {span}
          </span>
        </p>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
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
