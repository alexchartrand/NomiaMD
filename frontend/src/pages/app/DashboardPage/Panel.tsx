import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// A titled dashboard card; `action` sits at the right of the title (a "Tout voir" link…).
export function Panel({
  title,
  action,
  className,
  children,
}: {
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className={cn("rounded-xl border border-border bg-card p-5", className)}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-heading text-base font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export const panelLinkClasses = "text-sm font-medium text-primary no-underline hover:underline";
