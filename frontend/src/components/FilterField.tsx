import type { ReactNode } from "react";

// Keeps a label glued to its field so a wrapping filter row never splits them apart.
export function FilterField({ htmlFor, label, children }: { htmlFor: string; label: string; children: ReactNode }) {
  return (
    <div className="flex shrink-0 items-center gap-2">
      <label htmlFor={htmlFor} className="text-sm text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}
