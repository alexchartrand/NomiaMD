import { GRID_TILE, gridCellLeft } from "./LedgerBackdrop";

// The hero's accents on top of LedgerBackdrop's grid: a teal glow behind the preview card and
// two amber grid squares.
export function HeroAccents() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div className="absolute top-[75%] left-1/2 aspect-square w-[34rem] -translate-1/2 rounded-full bg-[radial-gradient(circle,var(--color-hero-glow)_0%,transparent_65%)] min-[881px]:top-1/2 min-[881px]:left-[calc(50%+19rem)]" />
      <span className="absolute size-7 bg-[color:var(--color-brand-accent)] opacity-20" style={{ top: 2 * GRID_TILE, left: gridCellLeft(5) }} />
      <span className="absolute size-7 bg-[color:var(--color-brand-accent)] opacity-15" style={{ top: 8 * GRID_TILE, left: gridCellLeft(18) }} />
    </div>
  );
}
