import { useId } from "react";
import { cn } from "@/lib/utils";

type LogoProps = {
  size?: number;
  className?: string;
};

// Bricolage Grotesque's own N (opsz 96, wght 800, wdth 100) as one outline, placed on the
// 100×100 tile; N_DIAGONAL is the part of that outline between the diagonal's two edges.
const N_OUTLINE =
  "M28.6 73 28.6 27 43.73 27 60.11 58.15 60.25 58.15 60.25 27 71.4 27 71.4 73 57.18 73 39.89 40.8 39.75 40.8 39.75 73Z";
const N_DIAGONAL = "M32.49 27 43.73 27 60.11 58.15 67.91 73 57.18 73 39.89 40.8Z";

// Cream → gold across the diagonal, mixed in OKLCH so it doesn't pass through a muddy beige.
const LETTER_STOPS: [number, string][] = [
  [0, "#f2efe7"],
  [0.261, "#f4eee7"],
  [0.356, "#f3e2ce"],
  [0.451, "#f1d6b4"],
  [0.546, "#efc99a"],
  [0.641, "#edbd7e"],
  [0.736, "#ebb061"],
  [0.831, "#e8a33d"],
];

/**
 * The brand mark: a teal tile carrying an N that warms from cream into gold — the stem it lands
 * on is the code that gets billed — with a soft shadow where the diagonal folds under that stem.
 * Fixed colours on purpose: the tile is its own ground, so it reads the same on light and dark
 * pages, and matches public/favicon.svg.
 */
export function Mark({ size = 32, className }: LogoProps) {
  // Gradient ids must be unique per instance: a duplicate id inside a hidden copy of the logo
  // (e.g. a collapsed mobile menu) would blank out the visible one in Chromium.
  const id = useId().replace(/:/g, "");
  const tile = `${id}-tile`;
  const letter = `${id}-letter`;
  const fold = `${id}-fold`;
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={className} aria-hidden="true">
      <defs>
        <linearGradient id={tile} gradientUnits="userSpaceOnUse" x1="6" y1="6" x2="94" y2="94">
          <stop offset="0" stopColor="#3f7382" />
          <stop offset="1" stopColor="#123e49" />
        </linearGradient>
        <linearGradient id={letter} gradientUnits="userSpaceOnUse" x1="28.6" y1="0" x2="71.4" y2="0">
          {LETTER_STOPS.map(([offset, color]) => (
            <stop key={offset} offset={offset} stopColor={color} />
          ))}
        </linearGradient>
        <linearGradient id={fold} gradientUnits="userSpaceOnUse" x1="32.49" y1="27" x2="67.91" y2="73">
          <stop offset="0" stopColor="#000" stopOpacity="0" />
          <stop offset="0.55" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.28" />
        </linearGradient>
      </defs>
      <rect x="6" y="6" width="88" height="88" rx="24" fill={`url(#${tile})`} />
      <path d={N_OUTLINE} fill={`url(#${letter})`} />
      <path d={N_DIAGONAL} fill={`url(#${fold})`} />
    </svg>
  );
}

/** Full lockup: mark + "Nomia" (bold, 86 % width) + "MD" knocked out of a gold block. */
export function Logo({ size = 32, className }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-[0.32em]", className)} style={{ fontSize: size * 0.85 }}>
      <Mark size={size} />
      <span className="inline-flex items-baseline font-logo leading-none">
        <span className="font-bold tracking-[-0.025em] text-[color:var(--color-primary-strong)] [font-stretch:86%] dark:text-foreground">
          Nomia
        </span>
        <span className="ml-[0.2em] self-center rounded-[0.2em] bg-[color:var(--color-brand-accent)] px-[0.32em] pt-[0.16em] pb-[0.12em] text-[0.5em] font-extrabold tracking-[0.04em] text-[color:var(--color-brand-ink)] [font-stretch:80%]">
          MD
        </span>
      </span>
    </span>
  );
}
