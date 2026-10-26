import { useEffect, useRef, useState } from "react";
import type { QuoteRange } from "./quoteLocator";

interface NotePanelProps {
  text: string;
  // The part of the note to mark: the supporting quote of the code being looked at.
  highlight?: QuoteRange | null;
  defaultOpen?: boolean;
}

// The note as it was received, collapsible, with the quote behind a proposed code marked in it.
export function NotePanel({ text, highlight = null, defaultOpen = false }: NotePanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const scroller = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLElement>(null);

  // Open, the note follows the highlight within its own box, never moving the page.
  useEffect(() => {
    const box = scroller.current;
    const marked = mark.current;
    if (!open || !box || !marked) return;
    const top = marked.offsetTop;
    const visible = top >= box.scrollTop && top + marked.offsetHeight <= box.scrollTop + box.clientHeight;
    if (!visible) box.scrollTo?.({ top: Math.max(0, top - box.clientHeight / 3), behavior: "smooth" });
  }, [open, highlight]);

  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="rounded-xl border border-border bg-card px-4 py-3"
    >
      <summary className="cursor-pointer font-heading font-semibold">Note reçue</summary>
      <div ref={scroller} className="relative mt-3 max-h-[60vh] overflow-y-auto">
        <pre className="m-0 font-sans text-[0.9rem] leading-relaxed whitespace-pre-wrap">
          {highlight ? (
            <>
              {text.slice(0, highlight.start)}
              <mark ref={mark} className="rounded-sm bg-[color:var(--color-warning-bg)] text-foreground">
                {text.slice(highlight.start, highlight.end)}
              </mark>
              {text.slice(highlight.end)}
            </>
          ) : (
            text
          )}
        </pre>
      </div>
    </details>
  );
}
