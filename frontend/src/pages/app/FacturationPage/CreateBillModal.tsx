import { useState } from "react";
import { createBill, describeError, listClaims, StaleBillSelectionError, type Claim } from "../../../api";
import {
  Banner,
  Button,
  Checkbox,
  Modal,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextField,
} from "../../../components";
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

  const allSelected = candidates != null && candidates.length > 0 && selection.size === candidates.length;
  const someSelected = selection.size > 0 && !allSelected;

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
            <span className="text-sm text-muted-foreground">
              {selection.size} facturation(s) sélectionnée(s) — total {totalSelected.toFixed(2)} $
            </span>
            <Button type="button" disabled={selection.size === 0 || submitting} onClick={handleSubmit}>
              {submitting ? "Génération..." : "Générer la facture"}
            </Button>
          </>
        )
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <label htmlFor="bill-date-from" className="text-sm text-muted-foreground">
          Du
        </label>
        <TextField
          id="bill-date-from"
          type="date"
          className="w-auto"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />

        <label htmlFor="bill-date-to" className="text-sm text-muted-foreground">
          Au
        </label>
        <TextField
          id="bill-date-to"
          type="date"
          className="w-auto"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />

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
          <TableHeader>
            <TableRow>
              <TableHead>
                <Checkbox
                  checked={allSelected ? true : someSelected ? "indeterminate" : false}
                  onCheckedChange={toggleAll}
                  aria-label="Tout sélectionner"
                />
              </TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Patient</TableHead>
              <TableHead>Codes</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {candidates.map((claim) => (
              <TableRow key={claim.id}>
                <TableCell>
                  <Checkbox
                    checked={selection.has(claim.id)}
                    onCheckedChange={() => toggle(claim.id)}
                    aria-label={`Sélectionner la facturation de ${claim.patient_full_name}`}
                  />
                </TableCell>
                <TableCell>{formatDate(claim.service_date)}</TableCell>
                <TableCell>{claim.patient_full_name}</TableCell>
                <TableCell>{claim.codes.map((c) => c.code).join(", ")}</TableCell>
                <TableCell>{claim.total_amount != null ? `${claim.total_amount.toFixed(2)} $` : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Modal>
  );
}
