import type { CodeHit } from "../../../api";
import { useFrequentCodes } from "./useFrequentCodes";

interface FrequentCodesProps {
  patientId: number;
  serviceDate: string | null;
  onAdd: (hit: CodeHit) => void;
  // Codes already on the claim: not offered again.
  excludeNumbers?: string[];
}

// One click adds one of the physician's most billed codes — the ones this patient may be billed.
export function FrequentCodes({ patientId, serviceDate, onAdd, excludeNumbers = [] }: FrequentCodesProps) {
  const { codes, loading, error } = useFrequentCodes(patientId, serviceDate);
  const offered = codes.filter((hit) => !excludeNumbers.includes(hit.number));

  if (loading || error || codes.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-semibold">Codes fréquents</span>
      {offered.length === 0 ? (
        <p className="m-0 text-sm text-muted-foreground">Tous vos codes fréquents sont déjà ajoutés.</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {offered.map((hit) => (
            <li key={hit.number}>
              <button
                type="button"
                className="flex w-full cursor-pointer items-baseline gap-3 rounded-lg border border-border bg-card px-3 py-2 text-left text-sm transition-colors hover:border-primary hover:bg-[color:var(--color-primary-tint)]"
                aria-label={`Ajouter le code ${hit.number} — ${hit.description}`}
                onClick={() => onAdd(hit)}
              >
                <span className="shrink-0 font-mono font-[650] whitespace-nowrap text-primary">+ {hit.number}</span>
                <span className="min-w-0 flex-1 text-muted-foreground">{hit.description}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
