import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, listAllClaims, type Claim } from "../../../api";
import type { Period } from "../../../utils/periods";

// Every claim in a period, whatever its status: the status, patient and source are
// filtered on the page so each status tab can count its claims. `reload` re-reads them in
// place, without blanking the list.
export function useClaims(period: Period) {
  const from = period.date_from ?? null;
  const to = period.date_to ?? null;
  const key = `${from}|${to}`;
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The period a response was asked for: a slow answer for a period the physician has
  // since left must not overwrite the new one's claims.
  const currentKey = useRef(key);
  currentKey.current = key;

  const reload = useCallback(async () => {
    const askedFor = key;
    try {
      const found = await listAllClaims({ date_from: from ?? undefined, date_to: to ?? undefined });
      if (currentKey.current !== askedFor) return;
      setClaims(found);
      setError(null);
    } catch (err) {
      if (currentKey.current === askedFor) setError(describeError(err));
    } finally {
      if (currentKey.current === askedFor) setLoading(false);
    }
  }, [key, from, to]);

  useEffect(() => {
    setLoading(true);
    setClaims([]);
    void reload();
  }, [reload]);

  return { claims, loading, error, reload };
}
