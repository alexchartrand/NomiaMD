import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface FormFieldProps {
  id: string;
  label: string;
  // A line under the field: what it's for, its format.
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}

// A labelled form control, the label above it and an optional hint below.
export function FormField({ id, label, hint, className, children }: FormFieldProps) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
      {hint && <p className="m-0 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
