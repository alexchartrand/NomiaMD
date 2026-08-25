import { forwardRef, type InputHTMLAttributes } from "react";

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

// forwardRef so a "select all" header checkbox can reach the DOM node and set
// .indeterminate — a property with no HTML attribute/prop equivalent.
export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { className, ...rest },
  ref,
) {
  const classes = ["checkbox", className].filter(Boolean).join(" ");
  return <input ref={ref} type="checkbox" className={classes} {...rest} />;
});
