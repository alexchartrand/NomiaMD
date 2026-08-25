import { Fragment, useEffect, useState } from "react";
import {
  BILLING_STATUSES,
  deleteBillingRecord,
  describeError,
  listBillingRecords,
  listPatients,
  updateBillingRecordStatus,
  type BillingRecord,
  type BillingRecordFilters,
  type BillingStatus,
  type Patient,
} from "../../api";
import { Banner, Button, Select, Table, TextField } from "../../components";

const STATUS_LABELS: Record<BillingStatus, string> = {
  brouillon: "Brouillon",
  facture: "Facturé",
};

export default function FacturationPage() {
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

  useEffect(loadRecords, [patientFilter, dateFrom, dateTo, statusFilter]);

  async function handleStatusChange(record: BillingRecord, status: BillingStatus) {
    try {
      await updateBillingRecordStatus(record.id, status);
      loadRecords();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  async function handleDelete(record: BillingRecord) {
    const confirmMessage =
      record.status === "facture"
        ? `${record.patient_full_name} est déjà facturé. Supprimer quand même cette facturation ?`
        : `Supprimer la facturation de ${record.patient_full_name} ? Cette action est irréversible.`;
    if (!window.confirm(confirmMessage)) return;
    try {
      await deleteBillingRecord(record.id);
      loadRecords();
    } catch (err) {
      setListError(describeError(err));
    }
  }

  return (
    <section className="page-panel">
      <h1>Facturation</h1>

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
            {records.map((record) => (
              <Fragment key={record.id}>
                <tr>
                  <td>{record.service_date}</td>
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
                    <Select
                      value={record.status}
                      onChange={(e) => handleStatusChange(record, e.target.value as BillingStatus)}
                    >
                      {BILLING_STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {STATUS_LABELS[s]}
                        </option>
                      ))}
                    </Select>
                  </td>
                  <td>
                    <div className="table-actions">
                      <Button type="button" variant="danger" onClick={() => handleDelete(record)}>
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
                            <em>&laquo; {c.supporting_quote} &raquo;</em>
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </Table>
      )}
    </section>
  );
}
