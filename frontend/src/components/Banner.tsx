import type { HTMLAttributes } from "react";
import { CircleAlert, CircleCheck, TriangleAlert, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Alert } from "./ui/alert";

type BannerTone = "error" | "warning" | "success";

type BannerProps = HTMLAttributes<HTMLDivElement> & {
  tone: BannerTone;
};

// shadcn's Alert only ships default/destructive variants, both on a white card. Every tone
// here is a tint of its own color instead (--color-*-bg / --color-*-text), with its icon.
const TONE_CLASSES: Record<BannerTone, string> = {
  error: "border-transparent bg-[color:var(--color-danger-bg)] text-[color:var(--color-danger)]",
  warning:
    "border-transparent bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
  success:
    "border-transparent bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]",
};

const TONE_ICONS: Record<BannerTone, LucideIcon> = {
  error: CircleAlert,
  warning: TriangleAlert,
  success: CircleCheck,
};

export function Banner({ tone, className, children, ...rest }: BannerProps) {
  const Icon = TONE_ICONS[tone];
  return (
    <Alert className={cn("px-3 py-2.5", TONE_CLASSES[tone], className)} {...rest}>
      <Icon aria-hidden />
      {/* One grid cell for the text, whatever mix of text and links it holds. */}
      <div className="[&_a]:font-semibold [&_a]:underline">{children}</div>
    </Alert>
  );
}
