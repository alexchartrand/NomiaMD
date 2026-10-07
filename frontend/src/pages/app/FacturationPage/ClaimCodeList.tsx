import type { ClaimCodeLine } from "../../../api";
import { formatMoney } from "../../../utils/money";
import { describeFee } from "./constants";

// A claim's snapshotted code lines, with their fee and the model's explanation — or, for a
// code the physician added from the code search, a mark saying so.
export function ClaimCodeList({ codes }: { codes: ClaimCodeLine[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {codes.map((c) => (
        <li key={c.code} className="flex flex-col gap-0.5">
          <span>
            <span className="mr-2 font-mono text-[0.85rem] font-semibold text-primary">{c.code}</span>
            {c.description}
            {c.fee_amount != null && <span className="font-semibold"> — {formatMoney(c.fee_amount)}</span>}
            {describeFee(c) && <span className="text-muted-foreground"> — {describeFee(c)}</span>}
          </span>
          {c.origin === "manual" ? (
            <span className="text-[0.85rem] text-muted-foreground">Ajouté manuellement</span>
          ) : (
            <em className="text-[0.85rem] text-muted-foreground">{c.explanation}</em>
          )}
        </li>
      ))}
    </ul>
  );
}
