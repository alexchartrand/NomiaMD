import type { InputHTMLAttributes } from "react";

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function Checkbox({ className, ...rest }: CheckboxProps) {
  const classes = ["checkbox", className].filter(Boolean).join(" ");
  return <input type="checkbox" className={classes} {...rest} />;
}
