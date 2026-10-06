import { Select } from "../../../components";
import type { ExtractedFee } from "../../../api";
import { buildFeeOptions, feeDetails, formatAmount, optionValue } from "./feeOptions";

// What a lone fee shows beside its amount; a fee with several lieux gets a selector instead.
function singleFeeDetails(fee: ExtractedFee): string {
  return [fee.lieux[0], feeDetails(fee)].filter(Boolean).join(" — ");
}

// What the picked option's label doesn't already say about its fee (role, context,
// majoration): a label only carries them when they're needed to tell options apart.
function pickedFeeDetails(fee: ExtractedFee, label: string): string {
  const details = feeDetails(fee);
  return details && !label.includes(details) ? details : "";
}

interface FeePickerProps {
  code: string;
  fees: ExtractedFee[];
  feeIndex: number;
  lieu: string | null;
  onSelect: (feeIndex: number, lieu: string | null) => void;
  disabled?: boolean;
}

// A code's fee: a selector when it has several (by lieu, then role/context), else its amount.
export function FeePicker({ code, fees, feeIndex, lieu, onSelect, disabled = false }: FeePickerProps) {
  const options = buildFeeOptions(fees);
  const picked = options.find((o) => o.feeIndex === feeIndex && o.lieu === lieu);
  const pickedDetails = picked ? pickedFeeDetails(fees[feeIndex], picked.label) : "";

  return (
    <div className="flex flex-wrap items-center gap-[0.6rem]">
      {options.length > 1 ? (
        <>
          <Select
            containerClassName="w-fit max-w-full"
            value={optionValue(feeIndex, lieu)}
            disabled={disabled}
            onChange={(event) => {
              const chosen = options.find((o) => optionValue(o.feeIndex, o.lieu) === event.target.value);
              if (chosen) onSelect(chosen.feeIndex, chosen.lieu);
            }}
            aria-label={`Tarif pour le code ${code}`}
          >
            {options.map((o) => (
              <option key={optionValue(o.feeIndex, o.lieu)} value={optionValue(o.feeIndex, o.lieu)}>
                {o.label}
              </option>
            ))}
          </Select>
          <span className="font-heading font-bold whitespace-nowrap">{formatAmount(fees[feeIndex])}</span>
          {pickedDetails && <span className="min-w-0 text-[0.85rem] text-muted-foreground">{pickedDetails}</span>}
        </>
      ) : fees.length === 1 ? (
        <>
          <span className="font-heading font-bold whitespace-nowrap">{formatAmount(fees[0])}</span>
          {singleFeeDetails(fees[0]) && (
            <span className="min-w-0 text-[0.85rem] text-muted-foreground">{singleFeeDetails(fees[0])}</span>
          )}
        </>
      ) : (
        <span className="font-heading font-bold">—</span>
      )}
    </div>
  );
}
