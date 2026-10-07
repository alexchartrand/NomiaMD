import { TriangleAlert } from "lucide-react";

// What the physician must confirm before billing a code: facts it depends on that couldn't
// be established from the patient's file or the physician's profile.
export function NeedsConfirmation({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <ul className="m-0 flex flex-col gap-1.5 rounded-lg bg-[color:var(--color-warning-bg)] px-3 py-2 text-[0.85rem] text-[color:var(--color-warning-text)]">
      {notes.map((note, noteIndex) => (
        <li key={noteIndex} className="flex list-none items-start gap-2">
          <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          <span>{note}</span>
        </li>
      ))}
    </ul>
  );
}
