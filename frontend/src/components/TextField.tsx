import type { ComponentProps, MouseEvent } from "react";
import { cn } from "@/lib/utils";
import { Input } from "./ui/input";

// Input types the browser edits with a picker (a calendar, a clock).
const PICKER_TYPES = new Set(["date", "month", "week", "time", "datetime-local"]);

// Input, plus: a date or time field opens its picker on a click anywhere in it, not only on
// its small icon — so the whole field shows the pointer. Typing the value still works.
export function TextField({ className, type, onClick, ...props }: ComponentProps<"input">) {
  const picker = type !== undefined && PICKER_TYPES.has(type);

  function openPicker(e: MouseEvent<HTMLInputElement>) {
    onClick?.(e);
    if (!picker || e.defaultPrevented || e.currentTarget.readOnly) return;
    try {
      e.currentTarget.showPicker?.();
    } catch {
      // Not allowed here (e.g. a cross-origin frame): the picker icon still works.
    }
  }

  return (
    <Input
      type={type}
      className={cn(picker && "cursor-pointer [&::-webkit-calendar-picker-indicator]:cursor-pointer", className)}
      onClick={openPicker}
      {...props}
    />
  );
}
