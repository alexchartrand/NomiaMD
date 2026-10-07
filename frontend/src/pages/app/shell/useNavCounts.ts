import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { getDashboard } from "../../../api";

// The sidebar's "waiting for you" count: the notes still to act on (the dashboard's to-do).
// Re-read on every page change, so it follows what the physician just did; a failed read
// just hides the pill.
export function useInboxCount(): number | null {
  const { pathname } = useLocation();
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let current = true;
    getDashboard()
      .then((dashboard) => current && setCount(dashboard.tasks.to_do))
      .catch(() => current && setCount(null));
    return () => {
      current = false;
    };
  }, [pathname]);

  return count;
}
