import { useEffect, useRef } from "react";

// Ctrl+Enter (⌘+Enter on a Mac) saves the review — and moves on, when there's a next one —
// from anywhere on the page, a field included: the physician never reaches for the mouse
// between two encounters.
export function useSaveShortcut(onSave: (() => void) | null) {
  const latest = useRef(onSave);
  latest.current = onSave;

  useEffect(() => {
    function handle(event: KeyboardEvent) {
      if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey) || event.repeat) return;
      if (!latest.current) return;
      event.preventDefault();
      latest.current();
    }
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, []);
}
