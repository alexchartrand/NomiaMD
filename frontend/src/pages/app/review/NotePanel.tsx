import { useEffect, useRef, useState } from "react";
import type { QuoteRange } from "./quoteLocator";

interface NotePanelProps {
  text: string;
  // The part of the note to mark: the supporting quote of the code being looked at.
  highlight?: QuoteRange | null;
  // Beside the review on a wide screen: always open, scrolling on its own. Otherwise a
  // collapsible section under it.
  docked?: boolean;
  defaultOpen?: boolean;
}

// The note as it was received, with the quote behind a proposed code marked in it.
export function NotePanel({ text, highlight = null, docked = false, defaultOpen = false }: NotePanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const scroller = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLElement>(null);

  // Docked, the note follows the highlight within its own box, never moving the page.
  useEffect(() => {
    const box = scroller.current;
    const marked = mark.current;
    if (!docked || !box || !marked) return;
    const top = marked.offsetTop;
    const visible = top >= box.scrollTop && top + marked.offsetHeight <= box.scrollTop + box.clientHeight;
    if (!visible) box.scrollTo?.({ top: Math.max(0, top - box.clientHeight / 3), behavior: "smooth" });
  }, [docked, highlight]);

  const body = (
    <pre className="m-0 font-mono text-sm whitespace-pre-wrap">
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
  );

  if (docked) {
    return (
      <section
        aria-label="Note reçue"
        className="sticky top-6 flex max-h-[calc(100dvh-3rem)] flex-col rounded-xl border border-border bg-card"
      >
        <h2 className="m-0 border-b border-border px-4 py-3 font-heading text-base font-semibold">Note reçue</h2>
        <div ref={scroller} className="relative overflow-y-auto px-4 py-3">
          {body}
        </div>
      </section>
    );
  }

  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      className="rounded-xl border border-border bg-card px-4 py-3"
    >
      <summary className="cursor-pointer font-heading font-semibold">Note reçue</summary>
      <div className="mt-3">{body}</div>
    </details>
  );
}
