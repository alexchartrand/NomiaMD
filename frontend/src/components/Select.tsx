import type { SelectHTMLAttributes } from "react";

type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function Select({ className, ...rest }: SelectProps) {
  const classes = ["select-field", className].filter(Boolean).join(" ");
  return <select className={classes} {...rest} />;
}
