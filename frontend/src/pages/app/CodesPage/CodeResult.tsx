import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { describeError, getCode, type CodeDetail, type CodeEligibility, type CodeHit } from "../../../api";
import { Banner } from "../../../components";
import { feeDetails, formatAmount } from "../review/feeOptions";

interface CodeResultProps {
  hit: CodeHit;
  expanded: boolean;
  onToggle: () => void;
}

// One search result; expanded, the code's entry from the manual — its fees, eligibility and
// when to use it. Its rules aren't shown yet: their extraction (ramq-ingestion) is incomplete.
export function CodeResult({ hit, expanded, onToggle }: CodeResultProps) {
  const panelId = `code-detail-${hit.number}`;
  return (
    <li className="list-none rounded-xl border border-border bg-card">
      <button
        type="button"
        className="flex w-full cursor-pointer items-start gap-3 bg-transparent px-4 py-3 text-left"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span className="rounded-lg border-2 border-foreground px-[0.5rem] py-[0.1rem] font-mono font-[650]">
          {hit.number}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-heading font-semibold">{hit.description}</span>
          {hit.header_path && <span className="text-xs text-muted-foreground">{hit.header_path}</span>}
        </span>
        {hit.fees[0] && <span className="font-heading font-bold whitespace-nowrap">{formatAmount(hit.fees[0])}</span>}
        <ChevronDown className={cn("mt-1 size-4 shrink-0 transition-transform", expanded && "rotate-180")} />
      </button>
      {expanded && (
        <div id={panelId} className="border-t border-border px-4 py-3">
          <CodeDetailPanel number={hit.number} />
        </div>
      )}
    </li>
  );
}

function CodeDetailPanel({ number }: { number: string }) {
  const [detail, setDetail] = useState<CodeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    getCode(number)
      .then((found) => current && setDetail(found))
      .catch((err) => current && setError(describeError(err)));
    return () => {
      current = false;
    };
  }, [number]);

  if (error) return <Banner tone="error">{error}</Banner>;
  if (!detail) return <p className="text-sm text-muted-foreground">Chargement...</p>;

  const eligibility = eligibilityLines(detail.eligibility);
  return (
    <div className="flex flex-col gap-4 text-sm">
      <Section title="Tarifs">
        {detail.fees.length === 0 ? (
          <p className="m-0 text-muted-foreground">Aucun tarif indiqué.</p>
        ) : (
          <ul className="m-0 flex flex-col gap-1 pl-5">
            {detail.fees.map((fee, i) => (
              <li key={i}>
                <span className="font-semibold">{formatAmount(fee)}</span>
                {fee.lieux.length > 0 && <> — {fee.lieux.join(", ")}</>}
                {feeDetails(fee) && <span className="text-muted-foreground"> — {feeDetails(fee)}</span>}
              </li>
            ))}
          </ul>
        )}
      </Section>
      {eligibility.length > 0 && (
        <Section title="Admissibilité">
          <ul className="m-0 flex flex-col gap-1 pl-5">
            {eligibility.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Section>
      )}
      {detail.when_to_use.length > 0 && (
        <Section title="Quand l'utiliser">
          <ul className="m-0 flex flex-col gap-1 pl-5">
            {detail.when_to_use.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="m-0 font-heading text-sm font-semibold">{title}</h3>
      {children}
    </div>
  );
}

function range(label: string, unit: string, min: number | null, max: number | null): string | null {
  if (min != null && max != null) return `${label} : de ${min} à ${max} ${unit}`;
  if (min != null) return `${label} : ${min} ${unit} ou plus`;
  if (max != null) return `${label} : ${max} ${unit} ou moins`;
  return null;
}

// The code's eligibility bounds in words; an axis it isn't bound on says nothing.
export function eligibilityLines(e: CodeEligibility): string[] {
  return [
    range("Âge du patient", "ans", e.min_age, e.max_age),
    range("Clientèle inscrite du médecin", "patients", e.min_panel_size, e.max_panel_size),
    e.requires_registered == null ? null : e.requires_registered ? "Patient inscrit auprès du médecin" : "Patient non inscrit auprès du médecin",
    e.requires_vulnerable == null ? null : e.requires_vulnerable ? "Patient vulnérable" : "Patient non vulnérable",
  ].filter((line): line is string => line !== null);
}
