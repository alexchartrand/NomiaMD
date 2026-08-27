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
import { Banner, Button, Select, Table, TextField } from "../../../components";
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
    if (!window.confirm(`Supprimer la facturation de ${claim.patient_full_name} ? Cette action est irréversible.`))
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
      <div className="filters-row">
        <label htmlFor="filter-patient">Patient</label>
        <Select id="filter-patient" value={patientFilter} onChange={(e) => setPatientFilter(e.target.value)}>
          <option value="">Tous les patients</option>
          {patients.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </Select>

        <label htmlFor="filter-date-from">Du</label>
        <TextField
          id="filter-date-from"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />

        <label htmlFor="filter-date-to">Au</label>
        <TextField id="filter-date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />

        <label htmlFor="filter-status">Statut</label>
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
        <p className="status-inline">Chargement...</p>
      ) : claims.length === 0 ? (
        <p>Aucune facturation enregistrée.</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Patient</th>
              <th>Codes</th>
              <th>Total</th>
              <th>Statut</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((claim) => {
              const deletable = claim.status === "brouillon";
              return (
                <Fragment key={claim.id}>
                  <tr>
                    <td>{formatDate(claim.service_date)}</td>
                    <td>{claim.patient_full_name}</td>
                    <td>
                      {claim.codes.map((c) => c.code).join(", ")}{" "}
                      <Button
                        type="button"
                        variant="link"
                        onClick={() => setExpandedId(expandedId === claim.id ? null : claim.id)}
                      >
                        Détails
                      </Button>
                    </td>
                    <td>{claim.total_amount != null ? `${claim.total_amount.toFixed(2)} $` : "—"}</td>
                    <td>
                      <span
                        className={`status-badge${claim.status === "facture" ? " status-badge-facture" : ""}`}
                      >
                        {STATUS_LABELS[claim.status]}
                      </span>
                    </td>
                    <td>
                      <div className="table-actions">
                        <Button
                          type="button"
                          variant="danger"
                          disabled={!deletable}
                          title={deletable ? undefined : "Cette facturation fait partie d'une facture générée."}
                          onClick={() => handleDelete(claim)}
                        >
                          Supprimer
                        </Button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === claim.id && (
                    <tr className="billing-details-row">
                      <td colSpan={6}>
                        <ul>
                          {claim.codes.map((c) => (
                            <li key={c.code}>
                              <span className="code-chip">{c.code}</span> {c.description}
                              {c.fee_amount != null && ` — ${c.fee_amount.toFixed(2)} $`}
                              {c.fee_when_to_use && <> — {c.fee_when_to_use}</>}
                              <br />
                              <em>{c.explanation}</em>
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </Table>
      )}
    </>
  );
}
