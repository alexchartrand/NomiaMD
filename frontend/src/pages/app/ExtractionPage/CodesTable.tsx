import { Table } from "../../../components";
import type { ExtractedCode } from "../../../api";

function confidenceBucket(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

interface CodesTableProps {
  codes: ExtractedCode[];
  selection: Set<number>;
  onToggle: (index: number) => void;
}

export function CodesTable({ codes, selection, onToggle }: CodesTableProps) {
  if (codes.length === 0) {
    return <p>Aucun code candidat n&rsquo;est clairement appuyé par cette transcription.</p>;
  }

  return (
    <Table>
      <thead>
        <tr>
          <th>Facturer</th>
          <th>Code</th>
          <th>Description</th>
          <th>Confiance</th>
          <th>Tarif</th>
          <th>Citation à l&rsquo;appui</th>
        </tr>
      </thead>
      <tbody>
        {codes.map((c, i) => (
          <tr key={i}>
            <td>
              <input
                type="checkbox"
                checked={selection.has(i)}
                onChange={() => onToggle(i)}
                aria-label={`Facturer le code ${c.code}`}
              />
            </td>
            <td className="code">{c.code}</td>
            <td>{c.description}</td>
            <td>
              <span className={`confidence-badge confidence-badge-${confidenceBucket(c.confidence)}`}>
                {(c.confidence * 100).toFixed(0)}%
              </span>
            </td>
            <td>{c.fee.amount != null ? `${c.fee.amount.toFixed(2)} $` : "—"}</td>
            <td>
              <em>&laquo; {c.supporting_quote} &raquo;</em>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
