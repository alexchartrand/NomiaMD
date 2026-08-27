import type { TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Textarea } from "./ui/textarea";

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

// Kept monospace by default (shadcn's Textarea defaults to the sans font) — matches this
// app's original .textarea-field convention used for transcript entry and chat input.
export function TextArea({ className, ...rest }: TextAreaProps) {
  return <Textarea className={cn("font-mono", className)} {...rest} />;
}
