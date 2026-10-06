import type { HTMLAttributes } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "primary" | "success" | "warning" | "danger";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-[color:var(--color-primary-tint)] text-primary",
  success: "bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]",
  warning: "bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
  danger: "bg-[color:var(--color-danger-bg)] text-[color:var(--color-danger)]",
};

type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
  icon?: LucideIcon;
};

// A small status pill: an encounter's or claim's status, a confidence level, days left…
export function Badge({ tone = "neutral", icon: Icon, className, children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[0.8rem] font-semibold",
        TONE_CLASSES[tone],
        className,
      )}
      {...rest}
    >
      {Icon && <Icon aria-hidden className="size-3.5" />}
      {children}
    </span>
  );
}
