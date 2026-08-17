import type { TableHTMLAttributes } from "react";

type TableProps = TableHTMLAttributes<HTMLTableElement>;

export function Table({ className, ...rest }: TableProps) {
  const classes = ["data-table", className].filter(Boolean).join(" ");
  return <table className={classes} {...rest} />;
}
