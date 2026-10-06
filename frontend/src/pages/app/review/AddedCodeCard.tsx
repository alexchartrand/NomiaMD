import { X } from "lucide-react";
import { Badge, Button } from "../../../components";
import type { ManualCodeEntry } from "./manualCodes";
import { FeePicker } from "./FeePicker";
import { NeedsConfirmation } from "./NeedsConfirmation";

interface AddedCodeCardProps {
  entry: ManualCodeEntry;
  onFeeSelected: (feeIndex: number, lieu: string | null) => void;
  onRemove: () => void;
  disabled?: boolean;
}

// A code the physician added from the code search: billed as long as it's listed.
export function AddedCodeCard({ entry, onFeeSelected, onRemove, disabled = false }: AddedCodeCardProps) {
  const { hit, feeIndex, lieu } = entry;
  return (
    <li className="flex items-start gap-3 rounded-xl border border-primary bg-[color:var(--color-primary-tint)] px-4 py-[0.9rem]">
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <span className="-rotate-[1.5deg] rounded-lg border-2 border-primary px-[0.55rem] py-[0.2rem] font-mono text-base font-[650] text-primary">
            {hit.number}
          </span>
          <Badge>Ajouté manuellement</Badge>
        </div>
        <span className="font-heading text-[0.95rem] leading-snug font-semibold">{hit.description}</span>

        <FeePicker
          code={hit.number}
          fees={hit.fees}
          feeIndex={feeIndex ?? 0}
          lieu={lieu}
          onSelect={onFeeSelected}
          disabled={disabled}
        />

        {hit.header_path && <p className="m-0 text-[0.85rem] text-muted-foreground">{hit.header_path}</p>}
        <NeedsConfirmation notes={hit.needs_confirmation} />
      </div>
      {!disabled && (
        <Button
          type="button"
          variant="ghost"
          className="size-8 p-0"
          onClick={onRemove}
          aria-label={`Retirer le code ${hit.number}`}
        >
          <X />
        </Button>
      )}
    </li>
  );
}
