import { useState } from "react";
import { searchCodes, type CodeHit } from "../../../api";
import { Search } from "lucide-react";
import { AppPage, AppPageHeader, Banner, TextField } from "../../../components";
import { useDebouncedSearch } from "../../../lib/useDebouncedSearch";
import { useFrequentCodes } from "../review/useFrequentCodes";
import { CodeResult } from "./CodeResult";

// Looking a code up without billing anything: by number (its first digits are enough) or by
// words of its description, with each code's fees and eligibility one click away — and the
// physician's most billed codes in a collapsible list, the same cards. No patient here, so
// every code of the manual in force is searched.
export default function CodesPage() {
  const [query, setQuery] = useState("");
  const { results, loading, error } = useDebouncedSearch(query.trim(), (q) => searchCodes({ q, limit: 50 }), {
    enabled: query.trim().length > 0,
  });
  const frequent = useFrequentCodes();
  // Which card is open, per list: a code can be both a frequent one and a search result.
  const [expanded, setExpanded] = useState<string | null>(null);

  const renderCards = (list: string, hits: CodeHit[]) => (
    <ul className="m-0 flex flex-col gap-2 p-0">
      {hits.map((hit) => {
        const key = `${list}:${hit.number}`;
        return (
          <CodeResult
            key={hit.number}
            hit={hit}
            expanded={expanded === key}
            onToggle={() => setExpanded(expanded === key ? null : key)}
          />
        );
      })}
    </ul>
  );

  return (
    <AppPage width="narrow" className="flex flex-col gap-5">
      <AppPageHeader
        title="Codes RAMQ"
        description="Recherchez un code du manuel des omnipraticiens par numéro ou par description : ses tarifs, son admissibilité et quand l'utiliser."
        className="mb-1"
      />

      <div className="relative">
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <TextField
          type="search"
          className="h-11 pl-9 text-base"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Numéro (ex. 0070) ou description (ex. suture plaie)..."
          aria-label="Rechercher un code RAMQ"
          autoFocus
        />
      </div>


      {loading ? (
        <p className="text-sm text-muted-foreground">Recherche...</p>
      ) : (
        !error &&
        query.trim() &&
        (results.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucun code trouvé.</p>
        ) : (
          renderCards("search", results)
        ))
      )}
      {/* Below the results, not between them and the field. */}
      {frequent.codes.length > 0 && (
        <details className="rounded-xl border border-border bg-card px-4 py-3">
          <summary className="cursor-pointer font-heading font-semibold">
            Codes fréquents ({frequent.codes.length})
          </summary>
          <div className="mt-3">{renderCards("frequent", frequent.codes)}</div>
        </details>
      )}
    </AppPage>
  );
}
