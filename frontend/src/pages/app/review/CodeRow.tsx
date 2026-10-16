import { useState, type HTMLAttributes, type ReactNode } from "react";
import { ChevronDown, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "../../../components";

export type CodeRowTone = "success" | "warning" | "danger" | "primary";

const STRIPES: Record<CodeRowTone, string> = {
  success: "border-l-[color:var(--color-success-text)]",
  warning: "border-l-[color:var(--color-warning-text)]",
  danger: "border-l-[color:var(--color-danger)]",
  primary: "border-l-primary",
};

// The list one group of rows sits in, framed together.
export const CODE_LIST_CLASS = "m-0 flex flex-col overflow-hidden rounded-lg border border-border p-0";

interface CodeRowProps extends Omit<HTMLAttributes<HTMLLIElement>, "children"> {
  code: string;
  description: string;
  // What bills it (a checkbox) and its id, which the code and description label; none for a
  // code billed as long as it's listed.
  control?: ReactNode;
  controlId?: string;
  // The left stripe, and what it means for a screen reader.
  tone: CodeRowTone;
  toneLabel: string;
  selected: boolean;
  amount: ReactNode;
  // The second line: the fee's lieu and details, or its selector.
  details?: ReactNode;
  warnings: string[];
  explanation?: string;
  // After the amount, e.g. a button removing the code.
  trailing?: ReactNode;
}

// One code on two lines: what it is and what it pays, then the fee's details, what to
// confirm and why it was proposed (folded) — scanned in one glance down the list.
export function CodeRow({
  code,
  description,
  control,
  controlId,
  tone,
  toneLabel,
  selected,
  amount,
  details,
  warnings,
  explanation,
  trailing,
  className,
  ...rest
}: CodeRowProps) {
  const [open, setOpen] = useState(false);
  const label = (
    <>
      <span className={cn("shrink-0 font-mono font-[650]", selected && "text-primary")}>{code}</span>
      <span className="min-w-0 flex-1 leading-snug font-medium">{description}</span>
    </>
  );
  return (
    <li
      className={cn(
        "flex list-none flex-col gap-1 border-b border-l-4 border-b-border px-3 py-2 transition-colors last:border-b-0",
        STRIPES[tone],
        selected && "bg-[color:var(--color-primary-tint)]",
        className,
      )}
      {...rest}
    >
      <div className="flex items-start gap-3">
        <span className="sr-only">{toneLabel}</span>
        {control && <span className="mt-[0.2rem] flex shrink-0">{control}</span>}
        {controlId ? (
          <label htmlFor={controlId} className="flex min-w-0 flex-1 cursor-pointer items-baseline gap-3">
            {label}
          </label>
        ) : (
          <span className="flex min-w-0 flex-1 items-baseline gap-3">{label}</span>
        )}
        <span className="shrink-0 font-heading font-bold whitespace-nowrap tabular-nums">{amount}</span>
        {trailing}
      </div>
      <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground empty:hidden", control && "pl-7")}>
        {details}
        {warnings.map((warning, i) => (
          <span key={i} className="inline-flex items-start gap-1 text-[color:var(--color-warning-text)]">
            <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
            {warning}
          </span>
        ))}
        {explanation && (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className="ml-auto text-muted-foreground"
            aria-expanded={open}
            aria-label={`Pourquoi le code ${code} ?`}
            onClick={() => setOpen((shown) => !shown)}
          >
            Pourquoi ?
            <ChevronDown aria-hidden className={cn("transition-transform", open && "rotate-180")} />
          </Button>
        )}
      </div>
      {explanation && open && <p className={cn("m-0 text-sm text-muted-foreground", control && "pl-7")}>{explanation}</p>}
    </li>
  );
}
