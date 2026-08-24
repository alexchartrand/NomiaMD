import type { HTMLAttributes } from "react";

type BannerTone = "error" | "warning" | "success";

type BannerProps = HTMLAttributes<HTMLParagraphElement> & {
  tone: BannerTone;
};

export function Banner({ tone, className, ...rest }: BannerProps) {
  const classes = ["banner", `banner-${tone}`, className].filter(Boolean).join(" ");
  return <p className={classes} {...rest} />;
}
