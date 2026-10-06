import { X } from "lucide-react";
import { Button } from "../../../components";
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
        <div className="flex items-start gap-3">
          <div className="flex min-w-0 flex-1 items-baseline gap-[0.6rem]">
            <span className="-rotate-[1.5deg] rounded-lg border-2 border-primary px-[0.55rem] py-[0.2rem] font-mono text-base font-[650] text-primary">
              {hit.number}
            </span>
            <span className="min-w-0 flex-1 font-heading font-semibold">{hit.description}</span>
          </div>
          <span className="inline-flex shrink-0 items-center rounded-full bg-muted px-[0.55rem] py-[0.15rem] text-[0.82rem] font-[650] whitespace-nowrap text-muted-foreground">
            Ajouté manuellement
          </span>
        </div>

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
