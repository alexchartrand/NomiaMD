import { Fragment, useEffect, useState } from "react";
import {
  CLAIM_STATUSES,
  deleteClaim,
  describeError,
  listClaims,
  listPatients,
  type Claim,
  type ClaimFilters,
  type ClaimStatus,
  type Patient,
} from "../../../api";
import {
  Banner,
  Button,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TextField,
} from "../../../components";
import { cn } from "@/lib/utils";
import { formatDate } from "../../../utils/date";
import { STATUS_LABELS } from "./constants";

interface RecordsTabProps {
  reloadSignal: number;
}

export function RecordsTab({ reloadSignal }: RecordsTabProps) {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientFilter, setPatientFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statusFilter, setStatusFilter] = useState<ClaimStatus | "">("");

  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    listPatients()
      .then(setPatients)
      .catch((err) => setListError(describeError(err)));
  }, []);

  function loadClaims() {
    setLoading(true);
    setListError(null);
    const filters: ClaimFilters = {};
    if (patientFilter) filters.patient_id = Number(patientFilter);
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    if (statusFilter) filters.status = statusFilter;

    listClaims(filters)
      .then(setClaims)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  // reloadSignal changes after a bill is generated/deleted on the other tab — claims may
  // have moved between "brouillon" and "soumis" without this tab knowing.
  useEffect(loadClaims, [patientFilter, dateFrom, dateTo, statusFilter, reloadSignal]);

  async function handleDelete(claim: Claim) {
    if (!window.confirm(`Supprimer la réclamation de ${claim.patient_full_name} ? Cette action est irréversible.`))
      return;
    try {
      await deleteClaim(claim.id);
      loadClaims();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <label htmlFor="filter-patient" className="text-sm text-muted-foreground">
          Patient
        </label>
        <Select id="filter-patient" value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)}>
          <option value="">Tous les patients</option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </Select>

        <label htmlFor="filter-date-from" className="text-sm text-muted-foreground">
          Du
        </label>
        <TextField
          id="filter-date-from"
          type="date"
          className="w-auto"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />

        <label htmlFor="filter-date-to" className="text-sm text-muted-foreground">
          Au
        </label>
        <TextField
          id="filter-date-to"
          type="date"
          className="w-auto"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />

        <label htmlFor="filter-status" className="text-sm text-muted-foreground">
          Statut
        </label>
        <Select
          id="filter-status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ClaimStatus | "")}
        >
          <option value="">Tous</option>
          {CLAIM_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
      </div>

      {listError && <Banner tone="error">{listError}</Banner>}

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement...</p>
      ) : claims.length === 0 ? (
        <p>Aucune réclamation enregistrée.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Patient</TableHead>
              <TableHead>Codes</TableHead>
              <TableHead>Total</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {claims.map((claim) => {
              const deletable = claim.status === "brouillon";
              return (
                <Fragment key={claim.id}>
                  <TableRow>
                    <TableCell>{formatDate(claim.service_date)}</TableCell>
                    <TableCell>{claim.patient_full_name}</TableCell>
                    <TableCell>
                      {claim.codes.map((c) => c.code).join(", ")}{" "}
                      <Button
                        type="button"
                        variant="link"
                        onClick={() => setExpandedId(expandedId === claim.id ? null : claim.id)}
                      >
                        Détails
                      </Button>
                    </TableCell>
                    <TableCell>{claim.total_amount != null ? `${claim.total_amount.toFixed(2)} $` : "—"}</TableCell>
                    <TableCell>
                      <span
                        className={cn(
                          "inline-block rounded-full px-[0.6rem] py-[0.15rem] text-[0.85rem]",
                          claim.status === "facture"
                            ? "bg-[color:var(--color-success-bg)] text-[color:var(--color-success-text)]"
                            : "bg-[color:var(--color-primary-tint)] text-primary",
                        )}
                      >
                        {STATUS_LABELS[claim.status]}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="danger"
                          disabled={!deletable}
                          title={deletable ? undefined : "Cette réclamation fait partie d'une facture générée."}
                          onClick={() => handleDelete(claim)}
                        >
                          Supprimer
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  {expandedId === claim.id && (
                    <TableRow className="bg-[color:var(--color-primary-tint)] hover:bg-[color:var(--color-primary-tint)]">
                      <TableCell colSpan={6}>
                        <ul className="m-0 space-y-2 pl-5">
                          {claim.codes.map((c) => (
                            <li key={c.code}>
                              <span className="font-mono text-[0.85rem] text-primary">{c.code}</span>{" "}
                              {c.description}
                              {c.fee_amount != null && ` — ${c.fee_amount.toFixed(2)} $`}
                              {c.fee_when_to_use && <> — {c.fee_when_to_use}</>}
                              <br />
                              <em>{c.explanation}</em>
                            </li>
                          ))}
                        </ul>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      )}
    </>
  );
}
