import { useState } from "react";
import { searchCodes, type CodeHit } from "../../../api";
import { Banner, TextField } from "../../../components";
import { useDebouncedSearch } from "../../../lib/useDebouncedSearch";
import { CodeResult } from "./CodeResult";

// Looking a code up without billing anything: by number (its first digits are enough) or by
// words of its description, with each code's rules, fees and eligibility one click away. No
// patient here, so every code of the manual in force is searched.
export default function CodesPage() {
  const [query, setQuery] = useState("");
  const { results, loading, error } = useDebouncedSearch(query.trim(), (q) => searchCodes({ q, limit: 50 }));
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <section className="flex max-w-[860px] flex-col gap-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold">Codes RAMQ</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Recherchez un code du manuel des omnipraticiens par numéro ou par description.
        </p>
      </div>

      <TextField
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Numéro (ex. 0070) ou description (ex. suture plaie)..."
        aria-label="Rechercher un code RAMQ"
        autoFocus
      />

      {error && <Banner tone="error">{error}</Banner>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Recherche...</p>
      ) : (
        !error && (
          <>
            {!query.trim() && results.length > 0 && (
              <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Vos codes fréquents</h2>
            )}
            {results.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {query.trim() ? "Aucun code trouvé." : "Tapez un numéro de code ou des mots de sa description."}
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
