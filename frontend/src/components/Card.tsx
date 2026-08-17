import type { HTMLAttributes } from "react";

type CardProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className, ...rest }: CardProps) {
  const classes = ["card", className].filter(Boolean).join(" ");
  return <div className={classes} {...rest} />;
}
