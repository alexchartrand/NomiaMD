import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, listShiftClaims, type ShiftClaim } from "../../../api";
import type { Period } from "../../../utils/periods";

// Every shift claim in a period, whatever its status — useClaims' twin for the shifts'
// own claims.
export function useShiftClaims(period: Period) {
  const from = period.date_from ?? null;
  const to = period.date_to ?? null;
  const key = `${from}|${to}`;
  const [shiftClaims, setShiftClaims] = useState<ShiftClaim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentKey = useRef(key);
  currentKey.current = key;

  const reload = useCallback(async () => {
    const askedFor = key;
    try {
      const found = await listShiftClaims({ date_from: from ?? undefined, date_to: to ?? undefined });
      if (currentKey.current !== askedFor) return;
      setShiftClaims(found);
      setError(null);
    } catch (err) {
      if (currentKey.current === askedFor) setError(describeError(err));
    } finally {
      if (currentKey.current === askedFor) setLoading(false);
    }
  }, [key, from, to]);

  useEffect(() => {
    setLoading(true);
    setShiftClaims([]);
    void reload();
  }, [reload]);

  return { shiftClaims, loading, error, reload };
}
