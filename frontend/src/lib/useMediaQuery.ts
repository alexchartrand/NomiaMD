import { useCallback, useSyncExternalStore } from "react";

// Whether a CSS media query matches, kept current as the window resizes. False where
// matchMedia doesn't exist (jsdom), so tests get the narrow layout.
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window.matchMedia !== "function") return () => {};
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () =>
    typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false,
  );
}
