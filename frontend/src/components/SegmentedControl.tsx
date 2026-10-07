import { cn } from "@/lib/utils";

export interface Segment<T extends string> {
  id: T;
  label: string;
}

interface SegmentedControlProps<T extends string> {
  segments: Segment<T>[];
  // null: none picked (a custom date range, say).
  value: T | null;
  onChange: (id: T) => void;
  ariaLabel: string;
  className?: string;
}

// A few mutually exclusive choices side by side: an inbox's period, a list's status.
export function SegmentedControl<T extends string>({ segments, value, onChange, ariaLabel, className }: SegmentedControlProps<T>) {
  return (
    <div role="group" aria-label={ariaLabel} className={cn("inline-flex flex-wrap rounded-lg bg-muted p-0.5", className)}>
      {segments.map((segment) => {
        const active = segment.id === value;
        return (
          <button
            key={segment.id}
            type="button"
            aria-pressed={active}
            className={cn(
              "cursor-pointer rounded-md border-none bg-transparent px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
              active && "bg-card text-primary shadow-sm hover:text-primary",
            )}
            onClick={() => onChange(segment.id)}
          >
            {segment.label}
          </button>
        );
      })}
    </div>
  );
}
