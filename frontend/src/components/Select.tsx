import type { SelectHTMLAttributes } from "react";
import { ChevronDownIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

// shadcn's Select primitive is a Radix combobox (SelectItem/onValueChange) that doesn't
// match this app's native <option>-list call sites (PatientsPage, ProfilePage,
// FacturationPage/RecordsTab) — kept as a native <select>, restyled to match Input's
// chrome, rather than rewriting those call sites' data shape for no functional benefit.
export function Select({ className, ...rest }: SelectProps) {
  return (
    <div className="relative w-full max-w-xs">
      <select
        className={cn(
          "h-8 w-full appearance-none rounded-lg border border-input bg-transparent px-2.5 py-1 pr-7 text-base text-foreground transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30",
          className,
        )}
        {...rest}
      />
      <ChevronDownIcon className="pointer-events-none absolute top-1/2 right-2 size-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}
