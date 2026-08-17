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
        <line stroke="var(--color-accent)" x1="20" y1="154" x2="80" y2="154" />
      </g>
    </svg>
  );
}

/** Full lockup: mark + "Nomia" (bold) + "md" (light, smaller, accent) on one baseline. */
export function Logo({ size = 32, className }: LogoProps) {
  return (
    <span className={`logo ${className ?? ""}`}>
      <Mark size={size} />
      <span className="logotype" style={{ fontSize: size * 0.85 }}>
        <span className="logotype-name">Nomia</span>
        <span className="logotype-credential">md</span>
      </span>
    </span>
  );
}
