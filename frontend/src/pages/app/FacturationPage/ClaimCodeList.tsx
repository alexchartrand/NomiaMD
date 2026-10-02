import type { ClaimCodeLine } from "../../../api";
import { describeFee } from "./constants";

// A claim's snapshotted code lines, with their fee and the model's explanation.
export function ClaimCodeList({ codes }: { codes: ClaimCodeLine[] }) {
  return (
    <ul className="m-0 space-y-2 pl-5">
      {codes.map((c) => (
        <li key={c.code}>
          <span className="font-mono text-[0.85rem] text-primary">{c.code}</span> {c.description}
          {c.fee_amount != null && ` — ${c.fee_amount.toFixed(2)} $`}
          {describeFee(c) && <> — {describeFee(c)}</>}
          <br />
          <em>{c.explanation}</em>
        </li>
      ))}
    </ul>
  );
}
