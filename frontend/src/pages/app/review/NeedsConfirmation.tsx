// What the physician must confirm before billing a code: facts it depends on that couldn't
// be established from the patient's file or the physician's profile.
export function NeedsConfirmation({ notes }: { notes: string[] }) {
  if (notes.length === 0) return null;
  return (
    <ul className="m-0 flex flex-col gap-1 pl-0 text-[0.85rem] text-[color:var(--color-warning-text)]">
      {notes.map((note, noteIndex) => (
        <li key={noteIndex} className="list-none">
          ⚠ {note}
        </li>
      ))}
    </ul>
  );
}
