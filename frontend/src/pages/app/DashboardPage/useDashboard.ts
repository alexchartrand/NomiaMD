import { useCallback, useEffect, useRef, useState } from "react";
import { describeError, getDashboard, type Dashboard } from "../../../api";

const POLL_INTERVAL_MS = 15_000;

// The dashboard summary. While a note is still being extracted ("reçu"), it re-reads it
// every ~15 s so the counts move without a reload — same cadence as the inbox.
export function useDashboard() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A response landing after the page was left must not set state.
  const mounted = useRef(true);

  const reload = useCallback(async () => {
    try {
      const found = await getDashboard();
      if (!mounted.current) return;
      setDashboard(found);
      setError(null);
    } catch (err) {
      if (mounted.current) setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void reload();
    return () => {
      mounted.current = false;
    };
  }, [reload]);

  const waiting = (dashboard?.tasks.extracting ?? 0) > 0;
  useEffect(() => {
    if (!waiting) return;
    const handle = setInterval(() => void reload(), POLL_INTERVAL_MS);
    return () => clearInterval(handle);
  }, [waiting, reload]);

  return { dashboard, error };
}
