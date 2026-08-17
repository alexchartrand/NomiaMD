import type { TextareaHTMLAttributes } from "react";

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function TextArea({ className, ...rest }: TextAreaProps) {
  const classes = ["textarea-field", className].filter(Boolean).join(" ");
  return <textarea className={classes} {...rest} />;
}
