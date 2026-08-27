import { cn } from "@/lib/utils";

type LogoProps = {
  size?: number;
  className?: string;
};

/** The brand mark: a shortlist of candidate codes narrowing down to one confirmed code tag. */
export function Mark({ size = 32, className }: LogoProps) {
  const height = (size * 176) / 220;
  return (
    <svg
      viewBox="0 0 220 176"
      width={size}
      height={height}
      className={className}
      aria-hidden="true"
    >
      <g fill="none" strokeWidth={15} strokeLinecap="round">
        <line stroke="var(--color-primary)" x1="20" y1="34" x2="200" y2="34" />
        <line stroke="var(--color-primary)" x1="20" y1="74" x2="160" y2="74" />
        <line stroke="var(--color-primary)" x1="20" y1="114" x2="120" y2="114" />
        <line stroke="var(--color-brand-accent)" x1="20" y1="154" x2="80" y2="154" />
      </g>
    </svg>
  );
}

/** Full lockup: mark + "Nomia" (bold) + "md" (light, smaller, accent) on one baseline. */
export function Logo({ size = 32, className }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-[0.6rem]", className)}>
      <Mark size={size} />
      <span
        className="inline-flex items-baseline font-heading leading-none tracking-[-0.03em]"
        style={{ fontSize: size * 0.85 }}
      >
        <span className="font-[650] text-foreground">Nomia</span>
        <span className="ml-[0.07em] text-[0.56em] font-light tracking-normal text-[color:var(--color-brand-accent)]">
          md
        </span>
      </span>
    </span>
  );
}
