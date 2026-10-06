import { cn } from "@/lib/utils";

export interface TabItem<T extends string> {
  id: T;
  label: string;
  // Shown in a pill beside the label; left out when undefined.
  count?: number;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  ariaLabel: string;
  className?: string;
}

// Underlined tabs over a page's lists (claims / bills, an inbox's statuses…).
export function Tabs<T extends string>({ items, value, onChange, ariaLabel, className }: TabsProps<T>) {
  return (
    <div role="tablist" aria-label={ariaLabel} className={cn("flex gap-1 overflow-x-auto border-b border-border", className)}>
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(item.id)}
            className={cn(
              "-mb-px inline-flex cursor-pointer items-center gap-2 border-b-2 border-transparent bg-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground",
              selected && "border-primary font-semibold text-primary hover:text-primary",
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span
                className={cn(
                  "rounded-full bg-muted px-1.5 py-px text-xs font-semibold tabular-nums text-muted-foreground",
                  selected && "bg-[color:var(--color-primary-tint)] text-primary",
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
