import { useEffect, useMemo, useState } from "react";
import { listEncounters } from "../../../api";
import { inboxOrder, readView } from "../InboxPage/inboxView";

export interface Neighbours {
  previousId: number | null;
  nextId: number | null;
  // 1-based place in the inbox's list, and its length.
  position: number;
  total: number;
}

// Where an encounter sits in the inbox list it was opened from (same period, filters and
// order), to step to the encounters around it. The list is read once per period, not after
// every save, so an encounter that leaves a "à traiter" filter once billed keeps its place.
// null while loading, or when the encounter isn't in that list (opened by URL).
export function useEncounterNeighbours(
  encounterId: number,
  inboxSearch: string,
): Neighbours | null {
  const { period, filters } = useMemo(
    () => readView(inboxSearch),
    [inboxSearch],
  );
  const from = period.date_from ?? null;
  const to = period.date_to ?? null;
  const [ids, setIds] = useState<number[]>([]);

  useEffect(() => {
    let current = true;
    listEncounters({ date_from: from, date_to: to })
      .then(
        (rows) =>
          current && setIds(inboxOrder(rows, filters).map((row) => row.id)),
      )
      .catch(() => current && setIds([]));
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from, to, filters.status, filters.source, filters.patient]);

  const index = ids.indexOf(encounterId);
  if (index < 0) return null;
  return {
    previousId: ids[index - 1] ?? null,
    nextId: ids[index + 1] ?? null,
    position: index + 1,
    total: ids.length,
  };
}
