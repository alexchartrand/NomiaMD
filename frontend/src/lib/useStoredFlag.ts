import { useCallback, useState } from "react";

// A yes/no UI preference remembered in this browser (the sidebar folded…). Storage can be
// missing or refuse access (private window, blocked site data): the flag then just lives
// for the session, starting from `initial`.
export function useStoredFlag(key: string, initial = false): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initial : stored === "1";
    } catch {
      return initial;
    }
  });

  const update = useCallback(
    (next: boolean) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, next ? "1" : "0");
      } catch {
        // Not remembered, still applied.
      }
    },
    [key],
  );

  return [value, update];
}
