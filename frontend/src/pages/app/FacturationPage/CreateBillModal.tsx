import { useEffect, useMemo, useState } from "react";
import { createBill, describeError, listClaims, StaleBillSelectionError, type Claim } from "../../../api";
import {
  Banner,
  Button,
  Checkbox,
  CodeChips,
  Modal,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextField,
} from "../../../components";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/money";

interface CreateBillModalProps {
  onClose: () => void;
  // The bill exists: the page closes the dialog (and shows the bills).
  onCreated: () => void;
}

// The backend hard-caps a single page at 200 (ClaimRepository.list_for_physician), so
// every draft is read page by page — none silently dropped.
const PAGE_SIZE = 200;

async function fetchAllDrafts(): Promise<Claim[]> {
  const all: Claim[] = [];
  let offset = 0;
  for (;;) {
    const page = await listClaims({ status: "brouillon", limit: PAGE_SIZE, offset });
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
    offset += PAGE_SIZE;
  }
  return all;
}

// The period covering every draft: its first and last service dates.
function spanOf(claims: Claim[]): { from: string; to: string } {
  const dates = claims.map((claim) => claim.service_date).sort();
  return { from: dates[0] ?? "", to: dates[dates.length - 1] ?? "" };
}

function rangeError(from: string, to: string): string | null {
  if (!from || !to) return "Les deux dates sont requises.";
  if (from > to) return "La date de début doit précéder la date de fin.";
  return null;
}

// Every draft claim, the period that covers them, all of them ticked: one click bills the
// lot. Narrowing the period narrows the list (and the selection) to it.
export function CreateBillModal({ onClose, onCreated }: CreateBillModalProps) {
  const [drafts, setDrafts] = useState<Claim[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    fetchAllDrafts()
      .then((found) => {
        if (!current) return;
        const span = spanOf(found);
        setDrafts(found);
        setDateFrom(span.from);
        setDateTo(span.to);
        setSelection(new Set(found.map((claim) => claim.id)));
      })
      .catch((err) => current && setLoadError(describeError(err)));
    return () => {
      current = false;
    };
  }, []);

  const periodError = drafts && drafts.length > 0 ? rangeError(dateFrom, dateTo) : null;
  const candidates = useMemo(
    () =>
      drafts && !periodError
        ? drafts.filter((claim) => claim.service_date >= dateFrom && claim.service_date <= dateTo)
        : [],
    [drafts, dateFrom, dateTo, periodError],
  );

  function changePeriod(from: string, to: string) {
    setDateFrom(from);
    setDateTo(to);
    setSubmitError(null);
    if (!drafts || rangeError(from, to)) return;
    // A new period starts with everything in it ticked.
    setSelection(new Set(drafts.filter((c) => c.service_date >= from && c.service_date <= to).map((c) => c.id)));
  }

  function toggle(id: number) {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const selected = candidates.filter((claim) => selection.has(claim.id));
  const allSelected = candidates.length > 0 && selected.length === candidates.length;
  const someSelected = selected.length > 0 && !allSelected;
  const totalSelected = selected.reduce((sum, claim) => sum + (claim.total_amount ?? 0), 0);

  function toggleAll() {
    setSelection(allSelected ? new Set() : new Set(candidates.map((claim) => claim.id)));
  }

  async function handleSubmit() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      await createBill({ start_date: dateFrom, end_date: dateTo, claim_ids: selected.map((claim) => claim.id) });
      onCreated();
    } catch (err) {
      if (err instanceof StaleBillSelectionError) {
        setSubmitError(`${err.message} La liste a été mise à jour, veuillez vérifier votre sélection.`);
        // The drafts went stale (a claim was billed/deleted elsewhere) — re-read them so the
        // physician isn't left selecting ids that no longer qualify.
        try {
          setDrafts(await fetchAllDrafts());
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
        drafts &&
        drafts.length > 0 && (
          <>
            <span className="text-sm text-muted-foreground">
              {selected.length} facturation(s) sélectionnée(s) — total {formatMoney(totalSelected)}
            </span>
            <Button type="button" disabled={selected.length === 0 || submitting || periodError !== null} onClick={handleSubmit}>
              {submitting ? "Génération..." : "Générer la facture"}
            </Button>
          </>
        )
      }
    >
      {loadError && <Banner tone="error">{loadError}</Banner>}
      {!drafts && !loadError && (
        <div aria-busy="true" aria-label="Chargement des brouillons" className="flex flex-col gap-2">
          <Skeleton className="h-9 w-80" />
          <Skeleton className="h-32 rounded-lg" />
        </div>
      )}
      {drafts && drafts.length === 0 && <p className="text-sm text-muted-foreground">Aucune réclamation en brouillon à facturer.</p>}

      {drafts && drafts.length > 0 && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="text-sm font-semibold">Période</span>
            <label htmlFor="bill-date-from" className="text-sm text-muted-foreground">
              Du
            </label>
            <TextField
              id="bill-date-from"
              type="date"
              className="w-auto"
              value={dateFrom}
              onChange={(e) => changePeriod(e.target.value, dateTo)}
            />
            <label htmlFor="bill-date-to" className="text-sm text-muted-foreground">
              Au
            </label>
            <TextField
              id="bill-date-to"
              type="date"
              className="w-auto"
              value={dateTo}
              onChange={(e) => changePeriod(dateFrom, e.target.value)}
            />
          </div>

          {periodError && <Banner tone="error">{periodError}</Banner>}
          {submitError && <Banner tone="error">{submitError}</Banner>}

          {!periodError && candidates.length === 0 && (
            <p className="text-sm text-muted-foreground">Aucune facturation non soumise dans cette période.</p>
          )}

          {candidates.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-border">
              <Table>
                <TableHeader className="bg-muted/40">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="pl-3">
                      <Checkbox
                        checked={allSelected ? true : someSelected ? "indeterminate" : false}
                        onCheckedChange={toggleAll}
                        aria-label="Tout sélectionner"
                      />
                    </TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Patient</TableHead>
                    <TableHead>Codes</TableHead>
                    <TableHead className="pr-3 text-right">Total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {candidates.map((claim) => (
                    <TableRow key={claim.id} className="cursor-pointer" onClick={(event) => {
                      if (!(event.target as HTMLElement).closest("button")) toggle(claim.id);
                    }}>
                      <TableCell className="pl-3">
                        <Checkbox
                          checked={selection.has(claim.id)}
                          onCheckedChange={() => toggle(claim.id)}
                          aria-label={`Sélectionner la facturation de ${claim.patient_full_name}`}
                        />
                      </TableCell>
                      <TableCell className="tabular-nums">{formatDate(claim.service_date)}</TableCell>
                      <TableCell className="font-semibold">{claim.patient_full_name}</TableCell>
                      <TableCell>
                        <CodeChips codes={claim.codes.map((c) => c.code)} max={3} />
                      </TableCell>
                      <TableCell className="pr-3 text-right tabular-nums">
                        {claim.total_amount != null ? formatMoney(claim.total_amount) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
