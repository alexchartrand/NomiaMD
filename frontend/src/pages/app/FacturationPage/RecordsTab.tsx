import { Fragment, useEffect, useState } from "react";
import {
  BILLING_STATUSES,
  deleteBillingRecord,
  describeError,
  listBillingRecords,
  listPatients,
  type BillingRecord,
  type BillingRecordFilters,
  type BillingStatus,
  type Patient,
} from "../../../api";
import { Banner, Button, Select, Table, TextField } from "../../../components";
import { formatDate } from "../../../utils/date";
import { STATUS_LABELS } from "./constants";

interface RecordsTabProps {
  reloadSignal: number;
}

export function RecordsTab({ reloadSignal }: RecordsTabProps) {
  const [records, setRecords] = useState<BillingRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientFilter, setPatientFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statusFilter, setStatusFilter] = useState<BillingStatus | "">("");

  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    listPatients()
      .then(setPatients)
      .catch((err) => setListError(describeError(err)));
  }, []);

  function loadRecords() {
    setLoading(true);
    setListError(null);
    const filters: BillingRecordFilters = {};
    if (patientFilter) filters.patient_id = Number(patientFilter);
    if (dateFrom) filters.date_from = dateFrom;
    if (dateTo) filters.date_to = dateTo;
    if (statusFilter) filters.status = statusFilter;

    listBillingRecords(filters)
      .then(setRecords)
      .catch((err) => setListError(describeError(err)))
      .finally(() => setLoading(false));
  }

  // reloadSignal changes after a bill is generated/deleted on the other tab — records may
  // have moved between "brouillon" and "soumis" without this tab knowing.
  useEffect(loadRecords, [patientFilter, dateFrom, dateTo, statusFilter, reloadSignal]);

  async function handleDelete(record: BillingRecord) {
    if (!window.confirm(`Supprimer la facturation de ${record.patient_full_name} ? Cette action est irréversible.`))
      return;
    try {
      await deleteBillingRecord(record.id);
      loadRecords();
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
          onChange={(e) => setStatusFilter(e.target.value as BillingStatus | "")}
        >
          <option value="">Tous</option>
          {BILLING_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
      </div>

      {listError && <Banner tone="error">{listError}</Banner>}

      {loading ? (
        <p className="status-inline">Chargement...</p>
      ) : records.length === 0 ? (
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
            {records.map((record) => {
              const deletable = record.status === "brouillon";
              return (
                <Fragment key={record.id}>
                  <tr>
                    <td>{formatDate(record.service_date)}</td>
                    <td>{record.patient_full_name}</td>
                    <td>
                      {record.codes.map((c) => c.code).join(", ")}{" "}
                      <Button
                        type="button"
                        variant="link"
                        onClick={() => setExpandedId(expandedId === record.id ? null : record.id)}
                      >
                        Détails
                      </Button>
                    </td>
                    <td>{record.total_amount != null ? `${record.total_amount.toFixed(2)} $` : "—"}</td>
                    <td>
                      <span
                        className={`status-badge${record.status === "facture" ? " status-badge-facture" : ""}`}
                      >
                        {STATUS_LABELS[record.status]}
                      </span>
                    </td>
                    <td>
                      <div className="table-actions">
                        <Button
                          type="button"
                          variant="danger"
                          disabled={!deletable}
                          title={deletable ? undefined : "Cette facturation fait partie d'une facture générée."}
                          onClick={() => handleDelete(record)}
                        >
                          Supprimer
                        </Button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === record.id && (
                    <tr className="billing-details-row">
                      <td colSpan={6}>
                        <ul>
                          {record.codes.map((c) => (
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
