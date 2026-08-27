import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Alert } from "./ui/alert";

type BannerTone = "error" | "warning" | "success";

type BannerProps = HTMLAttributes<HTMLDivElement> & {
  tone: BannerTone;
};

// shadcn's Alert only ships default/destructive variants. warning/success reuse this
// app's own tone colors (--color-warning-*/--color-success-*, no shadcn equivalent)
// layered on top via arbitrary-value classes rather than shadcn's default/destructive.
const TONE_CLASSES: Record<BannerTone, string> = {
  error: "",
  warning:
    "border-transparent bg-[color:var(--color-warning-bg)] text-[color:var(--color-warning-text)]",
  success:
    "border-transparent bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]",
};

export function Banner({ tone, className, ...rest }: BannerProps) {
  return (
    <Alert
      variant={tone === "error" ? "destructive" : "default"}
      className={cn(TONE_CLASSES[tone], className)}
      {...rest}
    />
  );
}
