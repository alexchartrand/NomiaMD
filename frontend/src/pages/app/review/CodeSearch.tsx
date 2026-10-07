import { TriangleAlert } from "lucide-react";
import { SearchCombobox } from "../../../components";
import { searchCodes, type CodeHit } from "../../../api";
import { formatAmount } from "./feeOptions";

interface CodeSearchProps {
  id?: string;
  onPick: (hit: CodeHit) => void;
  // With a patient, only the codes they may be billed on serviceDate are offered.
  patientId?: number | null;
  serviceDate?: string | null;
  // Codes already on the claim: not offered again.
  excludeNumbers?: string[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

// The indicative amount a search hit shows: its first fee, and how many others it has.
function feeSummary(hit: CodeHit): string | null {
  if (hit.fees.length === 0) return null;
  const first = formatAmount(hit.fees[0]);
  return hit.fees.length > 1 ? `${first} (+${hit.fees.length - 1} tarif${hit.fees.length > 2 ? "s" : ""})` : first;
}

function HitRow({ hit }: { hit: CodeHit }) {
  const fee = feeSummary(hit);
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-baseline gap-2">
        <span className="font-mono font-[650]">{hit.number}</span>
        <span className="min-w-0 flex-1">{hit.description}</span>
        {fee && <span className="shrink-0 font-heading font-semibold whitespace-nowrap">{fee}</span>}
      </div>
      {hit.header_path && <span className="truncate text-xs text-muted-foreground">{hit.header_path}</span>}
      {hit.needs_confirmation.length > 0 && (
        <span className="flex items-start gap-1 text-xs text-[color:var(--color-warning-text)]">
          <TriangleAlert aria-hidden className="mt-px size-3 shrink-0" />
          À confirmer : {hit.needs_confirmation.join(" ; ")}
        </span>
      )}
    </div>
  );
}

// Finds a RAMQ code by number (its first digits are enough) or by words of its description.
// Before anything is typed, offers the physician's most billed codes.
export function CodeSearch({
  id,
  onPick,
  patientId,
  serviceDate,
  excludeNumbers = [],
  placeholder,
  className,
  disabled,
}: CodeSearchProps) {
  const excluded = new Set(excludeNumbers);
  return (
    <SearchCombobox<CodeHit>
      id={id}
      search={async (q) =>
        (await searchCodes({ q, patientId, serviceDate, limit: 20 })).filter((hit) => !excluded.has(hit.number))
      }
      dependencyKey={`${patientId ?? ""}|${serviceDate ?? ""}|${[...excluded].join(",")}`}
      itemKey={(hit) => hit.number}
      renderItem={(hit) => <HitRow hit={hit} />}
      onPick={onPick}
      minChars={0}
      emptyText={(q) => (q ? "Aucun code trouvé" : "Tapez un numéro de code ou des mots de sa description")}
      emptyQueryHeading="Codes fréquents"
      placeholder={placeholder ?? "Numéro ou description du code..."}
      ariaLabel="Rechercher un code RAMQ"
      className={className ?? "max-w-none"}
      disabled={disabled}
    />
  );
}
