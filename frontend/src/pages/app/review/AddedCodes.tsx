import type { CodeHit } from "../../../api";
import { AddedCodeCard } from "./AddedCodeCard";
import { CodeSearch } from "./CodeSearch";
import type { ManualCodeEntry } from "./manualCodes";

interface AddedCodesProps {
  entries: ManualCodeEntry[];
  onAdd: (hit: CodeHit) => void;
  onRemove: (number: string) => void;
  onFeeSelected: (number: string, feeIndex: number, lieu: string | null) => void;
  // Who and when the codes are for: the search only offers what the patient may be billed.
  patientId: number | null;
  serviceDate: string | null;
  // Codes already on the claim some other way (the proposed ones): not offered again.
  excludeNumbers?: string[];
  searchLabel?: string;
  disabled?: boolean;
}

// The codes picked from the code search, and the search to add more.
export function AddedCodes({
  entries,
  onAdd,
  onRemove,
  onFeeSelected,
  patientId,
  serviceDate,
  excludeNumbers = [],
  searchLabel = "Ajouter un code",
  disabled = false,
}: AddedCodesProps) {
  return (
    <div className="flex flex-col gap-3">
      {entries.length > 0 && (
        <ul className="m-0 flex flex-col gap-3 p-0">
          {entries.map((entry) => (
            <AddedCodeCard
              key={entry.hit.number}
              entry={entry}
              onFeeSelected={(feeIndex, lieu) => onFeeSelected(entry.hit.number, feeIndex, lieu)}
              onRemove={() => onRemove(entry.hit.number)}
              disabled={disabled}
            />
          ))}
        </ul>
      )}
      {!disabled && (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="add-code-search" className="text-sm font-semibold">
            + {searchLabel}
          </label>
          <CodeSearch
            id="add-code-search"
            onPick={onAdd}
            patientId={patientId}
            serviceDate={serviceDate}
            excludeNumbers={[...excludeNumbers, ...entries.map((e) => e.hit.number)]}
          />
        </div>
      )}
    </div>
  );
}
