import { useState } from "react";
import { searchCodes, type CodeHit } from "../../../api";
import { Banner, Select, TextField } from "../../../components";
import { useDebouncedSearch } from "../../../lib/useDebouncedSearch";
import { useFrequentCodes } from "../review/useFrequentCodes";
import { CodeResult } from "./CodeResult";

// Looking a code up without billing anything: by number (its first digits are enough) or by
// words of its description, with each code's fees and eligibility one click away — or one of
// the physician's most billed codes, from a dropdown. No patient here, so every code of the
// manual in force is searched.
export default function CodesPage() {
  const [query, setQuery] = useState("");
  const { results, loading, error } = useDebouncedSearch(query.trim(), (q) => searchCodes({ q, limit: 50 }), {
    enabled: query.trim().length > 0,
  });
  const frequent = useFrequentCodes();
  const [expanded, setExpanded] = useState<string | null>(null);

  // A frequent code is looked up by its number, and opened straight away.
  function showFrequent(number: string) {
    if (!number) return;
    setQuery(number);
    setExpanded(number);
  }

  return (
    <section className="flex max-w-[860px] flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Codes RAMQ</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Recherchez un code du manuel des omnipraticiens par numéro ou par description.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <TextField
          type="search"
          className="min-w-[16rem] flex-1"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Numéro (ex. 0070) ou description (ex. suture plaie)..."
          aria-label="Rechercher un code RAMQ"
          autoFocus
        />
        {frequent.codes.length > 0 && (
          <Select
            containerClassName="max-w-[22rem]"
            aria-label="Codes fréquents"
            value=""
            onChange={(e) => showFrequent(e.target.value)}
          >
            <option value="">Codes fréquents…</option>
            {frequent.codes.map((hit) => (
              <option key={hit.number} value={hit.number}>
                {hit.number} — {hit.description}
              </option>
            ))}
          </Select>
        )}
      </div>

      {error && <Banner tone="error">{error}</Banner>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Recherche...</p>
      ) : (
        !error && (
          <>
            {!query.trim() ? (
              <p className="text-sm text-muted-foreground">
                Tapez un numéro de code ou des mots de sa description, ou choisissez un de vos codes fréquents.
              </p>
            ) : results.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Aucun code trouvé.
              </p>
            ) : (
              <ul className="m-0 flex flex-col gap-2 p-0">
                {results.map((hit: CodeHit) => (
                  <CodeResult
                    key={hit.number}
                    hit={hit}
                    expanded={expanded === hit.number}
                    onToggle={() => setExpanded(expanded === hit.number ? null : hit.number)}
                  />
                ))}
              </ul>
            )}
          </>
        )
      )}
    </section>
  );
}
