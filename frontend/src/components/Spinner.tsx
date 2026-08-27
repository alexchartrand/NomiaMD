import { Loader2 } from "lucide-react";

type SpinnerProps = {
  label?: string;
};

export function Spinner({ label }: SpinnerProps) {
  return (
    <span className="inline-flex items-center gap-1.5" role="status">
      <Loader2 className="size-4 animate-spin text-muted-foreground" />
      {label && <span className="text-sm text-muted-foreground">{label}</span>}
    </span>
  );
}
