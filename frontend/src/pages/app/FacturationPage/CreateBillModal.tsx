import { useEffect, useRef, useState } from "react";
import { createBill, describeError, listClaims, StaleBillSelectionError, type Claim } from "../../../api";
import { Banner, Button, Checkbox, Modal, Table, TextField } from "../../../components";
import { formatDate } from "../../../utils/date";

interface CreateBillModalProps {
  onClose: () => void;
  onCreated: () => void;
}

// The backend hard-caps a single page at 200 (ClaimRepository.list_for_physician),
// so a date range with more unbilled claims than that needs several pages to avoid
// silently truncating the candidate list.
const PAGE_SIZE = 200;

async function fetchAllUnsubmitted(dateFrom: string, dateTo: string): Promise<Claim[]> {
  const all: Claim[] = [];
  let offset = 0;
  for (;;) {
    const page = await listClaims({
      date_from: dateFrom,
      date_to: dateTo,
      status: "brouillon",
      limit: PAGE_SIZE,
      offset,
    });
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
  }
  return all;
}

export function CreateBillModal({ onClose, onCreated }: CreateBillModalProps) {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [rangeError, setRangeError] = useState<string | null>(null);

  const [candidates, setCandidates] = useState<Claim[] | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(false);

  const [selection, setSelection] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const selectAllRef = useRef<HTMLInputElement>(null);

  async function handleSearch() {
    setRangeError(null);
    setSubmitError(null);
    if (!dateFrom || !dateTo) {
      setRangeError("Les deux dates sont requises.");
      return;
    }
    if (dateFrom > dateTo) {
      setRangeError("La date de début doit précéder la date de fin.");
      return;
    }

    setLoadingCandidates(true);
    try {
      const found = await fetchAllUnsubmitted(dateFrom, dateTo);
      setCandidates(found);
      setSelection(new Set());
    } catch (err) {
      setRangeError(describeError(err));
    } finally {
      setLoadingCandidates(false);
    }
  }

  function toggle(id: number) {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (!candidates) return;
    setSelection((prev) => (prev.size === candidates.length ? new Set() : new Set(candidates.map((r) => r.id))));
  }

  useEffect(() => {
    if (selectAllRef.current && candidates) {
      selectAllRef.current.indeterminate = selection.size > 0 && selection.size < candidates.length;
    }
  }, [selection, candidates]);

  const totalSelected = candidates
    ? candidates
        .filter((r) => selection.has(r.id))
        .reduce((sum, r) => sum + (r.total_amount ?? 0), 0)
    : 0;

  async function handleSubmit() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createBill({
        start_date: dateFrom,
        end_date: dateTo,
        claim_ids: Array.from(selection),
      });
      onCreated();
      onClose();
    } catch (err) {
      if (err instanceof StaleBillSelectionError) {
        setSubmitError(`${err.message} La liste a été mise à jour, veuillez vérifier votre sélection.`);
        // The candidate set went stale (a claim was billed/deleted elsewhere) — refresh it
        // so the physician isn't left selecting ids that no longer qualify.
        try {
          const found = await fetchAllUnsubmitted(dateFrom, dateTo);
          setCandidates(found);
          setSelection(new Set());
        } catch {
          // Keep the stale-selection error visible; a refresh failure here isn't the
          // physician's primary problem.
        }
      } else {
        setSubmitError(describeError(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      title="Créer une facture"
      onClose={onClose}
      footer={
        candidates && (
          <>
            <span className="status-inline">
              {selection.size} facturation(s) sélectionnée(s) — total {totalSelected.toFixed(2)} $
            </span>
            <Button type="button" disabled={selection.size === 0 || submitting} onClick={handleSubmit}>
              {submitting ? "Génération..." : "Générer la facture"}
            </Button>
          </>
        )
      }
    >
      <div className="filters-row">
        <label htmlFor="bill-date-from">Du</label>
        <TextField id="bill-date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />

        <label htmlFor="bill-date-to">Au</label>
        <TextField id="bill-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />

        <Button type="button" variant="secondary" onClick={handleSearch} disabled={loadingCandidates}>
          {loadingCandidates ? "Recherche..." : "Rechercher"}
        </Button>
      </div>

      {rangeError && <Banner tone="error">{rangeError}</Banner>}
      {submitError && <Banner tone="error">{submitError}</Banner>}

      {candidates && candidates.length === 0 && (
        <p>Aucune facturation non soumise dans cette période.</p>
      )}

      {candidates && candidates.length > 0 && (
        <Table>
          <thead>
            <tr>
              <th>
                <Checkbox
                  ref={selectAllRef}
                  checked={selection.size === candidates.length}
                  onChange={toggleAll}
                  aria-label="Tout sélectionner"
                />
              </th>
              <th>Date</th>
              <th>Patient</th>
              <th>Codes</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((claim) => (
              <tr key={claim.id}>
                <td>
                  <Checkbox
                    checked={selection.has(claim.id)}
                    onChange={() => toggle(claim.id)}
                    aria-label={`Sélectionner la facturation de ${claim.patient_full_name}`}
                  />
                </td>
                <td>{formatDate(claim.service_date)}</td>
                <td>{claim.patient_full_name}</td>
                <td>{claim.codes.map((c) => c.code).join(", ")}</td>
                <td>{claim.total_amount != null ? `${claim.total_amount.toFixed(2)} $` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Modal>
  );
}
