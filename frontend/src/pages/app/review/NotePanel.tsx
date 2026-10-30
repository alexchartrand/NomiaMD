import { useEffect, useRef, useState } from "react";
import { clinicDayOf, formatDate } from "../../../utils/date";
import type { QuoteRange } from "./quoteLocator";

interface NotePanelProps {
  // null: the note's text was removed past its retention period, on `scrubbedAt`.
  text: string | null;
  scrubbedAt?: string | null;
  // The part of the note to mark: the supporting quote of the code being looked at.
  highlight?: QuoteRange | null;
  defaultOpen?: boolean;
}

// The note as it was received, collapsible, with the quote behind a proposed code marked in it.
export function NotePanel({ text, scrubbedAt = null, highlight = null, defaultOpen = false }: NotePanelProps) {
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

  if (text === null) return <ScrubbedNote scrubbedAt={scrubbedAt} />;

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

// The note's text is gone (retention), its codes and claim aren't: say so where the note was.
export function ScrubbedNote({ scrubbedAt }: { scrubbedAt: string | null }) {
  return (
    <p className="m-0 rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
      Note retirée{scrubbedAt ? ` le ${formatDate(clinicDayOf(scrubbedAt))}` : ""} (durée de conservation
      atteinte). Les codes et la facturation sont conservés ; réimportez la note depuis le DMÉ au besoin.
    </p>
  );
}
