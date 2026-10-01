import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, listEncounters, type EncounterPeriod, type EncounterRow } from "../../../api";

const POLL_INTERVAL_MS = 15_000;

// A period's encounters. While any is still "reçu" (its extraction queued, not done), it
// re-reads the list every ~15 s so rows turn "prêt" without a reload.
export function useInbox(period: EncounterPeriod) {
  const from = period.date_from ?? null;
  const to = period.date_to ?? null;
  const key = `${from}|${to}`;
  const [rows, setRows] = useState<EncounterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // The period a response was asked for: a slow answer for a period the physician has
  // since left must not overwrite the new one's rows.
  const currentKey = useRef(key);
  currentKey.current = key;

  const reload = useCallback(async () => {
    const askedFor = key;
    try {
      const found = await listEncounters({ date_from: from, date_to: to });
      if (currentKey.current !== askedFor) return;
      setRows(found);
      setError(null);
    } catch (err) {
      if (currentKey.current === askedFor) setError(describeError(err));
    } finally {
      if (currentKey.current === askedFor) setLoading(false);
    }
  }, [key, from, to]);

  useEffect(() => {
    setLoading(true);
    setRows([]);
    void reload();
  }, [reload]);

  const waiting = rows.some((row) => row.status === "reçu");
  useEffect(() => {
    if (!waiting) return;
    const handle = setInterval(() => void reload(), POLL_INTERVAL_MS);
    return () => clearInterval(handle);
  }, [waiting, reload]);

  return { rows, loading, error, reload };
}
