import type { ReactNode } from "react";

// A fine ledger grid behind the top of the landing page (hero + "Pourquoi NomiaMD"), so the
// two sections read as one block. It shows around the hero's preview card and fades out from
// there, reaching down into the next section; the mask is sized in px from the top so it
// keeps that reach however tall the block gets. Its tiles are anchored on the page's centre line (offset half a
// tile), so anything placed with `gridCellLeft` in whole tiles lands exactly on a square.
export const GRID_TILE = 28;

/** Left edge of the grid square `columns` tiles right of the centre line (negative = left). */
export function gridCellLeft(columns: number) {
  return `calc(50% - ${GRID_TILE / 2}px + ${columns * GRID_TILE}px)`;
}

export function LedgerBackdrop({ children }: { children: ReactNode }) {
  return (
    // overflow-hidden clips the hero's glow, which reaches past the right edge on narrow screens.
    <div className="relative isolate overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 [mask-image:radial-gradient(70%_760px_at_50%_720px,#000_35%,transparent_85%)] min-[881px]:[mask-image:radial-gradient(55%_720px_at_68%_300px,#000_35%,transparent_85%)]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-hero-grid) 1px, transparent 1px), linear-gradient(90deg, var(--color-hero-grid) 1px, transparent 1px)",
          backgroundSize: `${GRID_TILE}px ${GRID_TILE}px`,
          backgroundPosition: "50% 0",
        }}
      />
      {children}
    </div>
  );
}
