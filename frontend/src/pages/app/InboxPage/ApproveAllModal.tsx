import { useEffect, useState } from "react";
import { createClaim, describeError, getEncounter, type EncounterDetail, type EncounterRow } from "../../../api";
import { Banner, Button, Modal, Spinner } from "../../../components";
import { formatDate } from "../../../utils/date";

type Outcome = { ok: true } | { ok: false; error: string };

interface ApproveAllModalProps {
  // The day's all_clean rows — the server's rule (app/encounters/readiness.py): the retained
  // codes are high-confidence, with nothing to confirm and one fee each; dated, no possible
  // duplicate.
  rows: EncounterRow[];
  onClose: () => void;
  // Called once claims were saved, so the inbox re-reads its statuses.
  onApproved: () => void;
}

// What approving bills: the codes the run retained (the review's preselection), never its
// other possible codes.
function retainedCodes(detail: EncounterDetail) {
  return (detail.extraction?.billing.result.codes ?? []).filter((c) => c.retained);
}

// Every retained code is billed at its only fee (fee_index null = the first, and only, one).
function approvable(detail: EncounterDetail): boolean {
  const codes = retainedCodes(detail);
  // all_clean already excludes these; checked again on what is actually about to be billed.
  return codes.length > 0 && codes.every((c) => c.needs_confirmation.length === 0 && c.fees.length <= 1);
}

export function ApproveAllModal({ rows, onClose, onApproved }: ApproveAllModalProps) {
  const [details, setDetails] = useState<EncounterDetail[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [outcomes, setOutcomes] = useState<Map<number, Outcome> | null>(null);

  useEffect(() => {
    Promise.all(rows.map((row) => getEncounter(row.id)))
      .then((found) => setDetails(found.filter(approvable)))
      .catch((err) => setLoadError(describeError(err)));
  }, [rows]);

  async function handleApprove() {
    if (!details) return;
    setApproving(true);
    const results = new Map<number, Outcome>();
    // One at a time: POST /claims checks "first claim for this patient on this date", and
    // two of these could be the same patient.
    for (const detail of details) {
      const extraction = detail.extraction!;
      try {
        await createClaim({
          extraction_run_id: extraction.extraction_run_id,
          service_date: detail.service_date!,
          selected_codes: retainedCodes(detail).map((c) => ({ code: c.code, fee_index: null })),
        });
        results.set(detail.id, { ok: true });
      } catch (err) {
        // A same-patient-same-day warning included: approving in bulk never overrides it.
        results.set(detail.id, { ok: false, error: describeError(err) });
      }
    }
    setOutcomes(results);
    setApproving(false);
    if ([...results.values()].some((r) => r.ok)) onApproved();
  }

  const done = outcomes !== null;
  const savedCount = outcomes ? [...outcomes.values()].filter((r) => r.ok).length : 0;

  return (
    <Modal
      title="Approuver les rencontres prêtes"
      onClose={onClose}
      footer={
        <>
          <span className="text-sm text-muted-foreground">
            {done
              ? `${savedCount} facturation${savedCount > 1 ? "s" : ""} enregistrée${savedCount > 1 ? "s" : ""}`
              : details
                ? `${details.length} rencontre${details.length > 1 ? "s" : ""} à facturer`
                : ""}
          </span>
          {done ? (
            <Button type="button" onClick={onClose}>
              Fermer
            </Button>
          ) : (
            <Button type="button" onClick={handleApprove} disabled={!details || details.length === 0 || approving}>
              {approving ? "Enregistrement..." : "Approuver et enregistrer"}
            </Button>
          )}
        </>
      }
    >
      {loadError && <Banner tone="error">{loadError}</Banner>}
      {!details && !loadError && <Spinner label="Chargement..." />}
      {details && details.length === 0 && <p>Aucune rencontre à approuver.</p>}
      {details && details.length > 0 && (
        <ul className="m-0 flex flex-col gap-3 p-0">
          {details.map((detail) => {
            const outcome = outcomes?.get(detail.id);
            return (
              <li key={detail.id} className="list-none rounded-lg border border-border px-4 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-semibold">{detail.patient?.full_name}</span>
                  <span className="text-sm text-muted-foreground">{formatDate(detail.service_date!)}</span>
                </div>
                <ul className="mt-1 mb-0 pl-4 text-sm">
                  {retainedCodes(detail).map((c) => (
                    <li key={c.code}>
                      <span className="font-mono font-[650]">{c.code}</span> — {c.description}
                    </li>
                  ))}
                </ul>
                {outcome?.ok && <p className="mt-1 mb-0 text-sm text-[color:var(--color-success-text)]">✓ Enregistrée</p>}
                {outcome && !outcome.ok && <p className="mt-1 mb-0 text-sm text-destructive">{outcome.error}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}
