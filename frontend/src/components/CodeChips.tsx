import { cn } from "@/lib/utils";

interface CodeChipsProps {
  codes: string[];
  // Past this many, the rest is a "+n".
  max?: number;
  className?: string;
}

// A row's RAMQ code numbers as small tinted chips (the landing page's inbox preview look).
export function CodeChips({ codes, max = 4, className }: CodeChipsProps) {
  const shown = codes.slice(0, max);
  const hidden = codes.length - shown.length;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      {shown.map((code) => (
        <span
          key={code}
          className="rounded-md bg-[color:var(--color-primary-tint)] px-1.5 py-0.5 font-mono text-[0.78rem] font-semibold text-primary"
        >
          {code}
        </span>
      ))}
      {hidden > 0 && (
        <span className="text-xs font-medium text-muted-foreground" title={codes.slice(max).join(", ")}>
          +{hidden}
        </span>
      )}
    </span>
  );
}
