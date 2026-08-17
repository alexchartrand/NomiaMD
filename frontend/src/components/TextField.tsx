import type { InputHTMLAttributes } from "react";

type TextFieldProps = InputHTMLAttributes<HTMLInputElement>;

export function TextField({ className, ...rest }: TextFieldProps) {
  const classes = ["text-field", className].filter(Boolean).join(" ");
  return <input className={classes} {...rest} />;
}
