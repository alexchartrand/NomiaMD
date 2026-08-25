import { Checkbox } from "../../../components";
import type { ExtractedCode } from "../../../api";

function confidenceBucket(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 0.85) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

interface CodesReviewProps {
  codes: ExtractedCode[];
  selection: Set<number>;
  onToggle: (index: number) => void;
}

export function CodesReview({ codes, selection, onToggle }: CodesReviewProps) {
  if (codes.length === 0) {
    return <p>Aucun code candidat n&rsquo;est clairement appuyé par cette transcription.</p>;
  }

  return (
    <ul className="code-cards">
      {codes.map((c, i) => {
        const checked = selection.has(i);
        return (
          <li key={i} className={`code-card${checked ? " code-card-selected" : ""}`}>
            <Checkbox
              className="code-card-checkbox"
              checked={checked}
              onChange={() => onToggle(i)}
              aria-label={`Facturer le code ${c.code}`}
            />

            <div className="code-card-body">
              <div className="code-card-header">
                <span className="code-stamp">{c.code}</span>
                <span className="code-card-title">{c.description}</span>
                <span className="code-card-fee">{c.fee.amount != null ? `${c.fee.amount.toFixed(2)} $` : "—"}</span>
              </div>

              <p className="code-card-quote">&laquo; {c.supporting_quote} &raquo;</p>

              <div className="code-card-footer">
                <span className={`confidence-badge confidence-badge-${confidenceBucket(c.confidence)}`}>
                  {(c.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
