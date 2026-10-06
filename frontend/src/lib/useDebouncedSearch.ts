import { useEffect, useRef, useState } from "react";
import { describeError } from "../api";

interface DebouncedSearchOptions {
  // Off: no request, and no results.
  enabled?: boolean;
  delay?: number;
  // Anything else the search depends on besides the query (a patient, a date…): a change
  // searches again. `search` itself may be a fresh closure on every render.
  dependencyKey?: string;
}

// Searches once typing pauses, rather than on every keystroke. A response that arrives after
// the query moved on is dropped, so an older, slower request never overwrites a newer one.
export function useDebouncedSearch<T>(
  query: string,
  search: (query: string) => Promise<T[]>,
  { enabled = true, delay = 250, dependencyKey = "" }: DebouncedSearchOptions = {},
) {
  const [results, setResults] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchRef = useRef(search);
  useEffect(() => {
    searchRef.current = search;
  });

  useEffect(() => {
    if (!enabled) {
      setResults([]);
      setLoading(false);
      return;
    }
    let current = true;
    setLoading(true);
    const handle = setTimeout(() => {
      searchRef.current(query)
        .then((found) => {
          if (!current) return;
          setResults(found);
          setError(null);
        })
        .catch((err) => current && setError(describeError(err)))
        .finally(() => current && setLoading(false));
    }, delay);
    return () => {
      current = false;
      clearTimeout(handle);
    };
  }, [query, enabled, delay, dependencyKey]);

  return { results, loading, error };
}
