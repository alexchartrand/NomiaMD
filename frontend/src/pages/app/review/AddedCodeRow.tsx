import { X } from "lucide-react";
import { Button } from "../../../components";
import type { ManualCodeEntry } from "./manualCodes";
import { CodeRow } from "./CodeRow";
import { FeeAmount, FeePicker } from "./FeePicker";

interface AddedCodeRowProps {
  entry: ManualCodeEntry;
  onFeeSelected: (feeIndex: number, lieu: string | null) => void;
  onRemove: () => void;
  disabled?: boolean;
}

// A code the physician added from the code search: billed as long as it's listed.
export function AddedCodeRow({ entry, onFeeSelected, onRemove, disabled = false }: AddedCodeRowProps) {
  const { hit, feeIndex, lieu } = entry;
  return (
    <CodeRow
      code={hit.number}
      description={hit.description}
      tone="primary"
      toneLabel="Ajouté manuellement"
      selected
      amount={<FeeAmount fees={hit.fees} feeIndex={feeIndex ?? 0} />}
      details={
        <>
          <FeePicker
            code={hit.number}
            fees={hit.fees}
            feeIndex={feeIndex ?? 0}
            lieu={lieu}
            onSelect={onFeeSelected}
            disabled={disabled}
          />
          {hit.header_path && <span className="min-w-0">{hit.header_path}</span>}
        </>
      }
      warnings={hit.needs_confirmation}
      trailing={
        !disabled && (
          <Button
            type="button"
            variant="ghost"
            className="-my-1 size-7 p-0"
            onClick={onRemove}
            aria-label={`Retirer le code ${hit.number}`}
          >
            <X />
          </Button>
        )
      }
    />
  );
}
